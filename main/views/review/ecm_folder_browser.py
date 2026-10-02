"""산출물 폴더 탐색: 프로젝트 root 폴더의 구조를 화면에 보여주고 파일 단위로 내려준다.

ECM 점검 페이지(/download-review/)와 KOLAS 페이지(/kolas/)의 상세 결과 팝업이 같이 쓴다.

- 목록: ECM 폴더는 폴더 목록 API 로, zip 은 **디스크에 저장하지 않고** 흘려받으며 파일 헤더만 읽어(ecm_zip_stream)
  구조를 만든다. ECM 은 Range 를 지원하지 않아 전송은 zip 크기만큼 일어나지만(194→ECM 약 41MB/s) 저장은 하지 않는다.
  zip 의 목록(이름·크기)은 짧게 기억(Django cache)해 폴더 이동은 다시 받지 않는다.
- 파일 하나: ECM 파일은 그대로 중계하고, zip 안의 파일은 zip 을 다시 흘려받으며 그 항목만 골라 보낸다.
- 중첩 zip: 바깥 zip 의 항목 데이터를 그대로 안쪽 zip 해석기에 먹인다(파이프라인). 임시 파일이 필요 없다.
- 폴더/여러 항목: 선택한 것들을 하나의 zip 으로 스트리밍한다. 같은 zip 에서 고른 항목은 한 번만 받는다.
- 보안: 화면에는 ECM OID 를 그대로 주지 않고 서버가 서명한 항목 토큰(ref)만 준다. 토큰은 만료되고 프로젝트 번호가
  묶여 있어, 목록에서 받은 항목(= 그 프로젝트 root 아래)만 열 수 있다.
"""

import contextvars
import hashlib
import logging
import os
import re
import threading
import time
import unicodedata
import zipfile
from contextlib import contextmanager
from pathlib import PurePosixPath

from django.conf import settings
from django.core import signing
from django.core.cache import cache

from main.views.review import ecm_zip_cache as zc
from main.views.review import ecm_zip_stream
from main.views.review.ecm_zip_cache import EntryRec, zip_cache
from main.views.review.ecm_http_client import build_client
from main.views.review.kolas_report_download import center_try_order
from main.views.testing.history_download import _safe_zip_part, _StreamingZipSink, _unique_arcname

logger = logging.getLogger(__name__)

TOKEN_SALT = "gscert.folder-browser"
TOKEN_MAX_AGE_SECONDS = 6 * 3600
CLIENT_TTL_SECONDS = 600
_current_sid = contextvars.ContextVar("folder_browser_sid", default="")
STREAM_CHUNK_BYTES = 1024 * 1024
MAX_NESTED_ZIP_DEPTH = 3
DEFAULT_ZIP_MAX_MB = 1024
DEFAULT_LIST_CACHE_SECONDS = 900
DEFAULT_LIST_WAIT_SECONDS = 540
DEFAULT_PREFETCH_MIN_MB = 30
NEAR_DONE_FRACTION = zc.NEAR_DONE_FRACTION
NEAR_DONE_WAIT_SECONDS = 120
DEFAULT_MAX_SELECTION = 200
DEFAULT_MAX_FILES_PER_DOWNLOAD = 5000

JUNK_PREFIXES = ("__MACOSX/",)
JUNK_BASENAME_PREFIXES = ("._",)


class BrowseError(Exception):
    """화면에 그대로 보여줄 수 있는 오류(상태 코드 포함)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# 서명된 항목 토큰
# ---------------------------------------------------------------------------
def make_ref(payload):
    return signing.dumps(payload, salt=TOKEN_SALT, compress=True)


def read_ref(token, project_number):
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.SignatureExpired as exc:
        raise BrowseError("항목 정보가 만료되었습니다. 폴더를 처음부터 다시 열어 주세요.", 400) from exc
    except signing.BadSignature as exc:
        raise BrowseError("올바르지 않은 항목입니다.", 400) from exc
    if not isinstance(payload, dict) or payload.get("p") != project_number:
        raise BrowseError("다른 프로젝트의 항목입니다.", 400)
    return payload


def _meta_to_token(meta):
    return {
        "n": meta.get("fileName", ""),
        "o": meta.get("fileOID") or meta.get("OID") or "",
        "s": meta.get("storageFileID", ""),
        "z": int(float(meta.get("fileSize") or 0)),
    }


def _meta_from_token(token_meta):
    return {
        "fileName": token_meta["n"],
        "fileOID": token_meta["o"],
        "storageFileID": token_meta["s"],
        "fileSize": token_meta["z"],
    }


# ---------------------------------------------------------------------------
# ECM 클라이언트 (센터별, 10분 재사용)
# ---------------------------------------------------------------------------
client_factory = build_client
_CLIENTS = {}
_CLIENT_LOCK = threading.Lock()


def get_client(center):
    now = time.monotonic()
    with _CLIENT_LOCK:
        entry = _CLIENTS.get(center)
        if entry and now - entry[1] < CLIENT_TTL_SECONDS:
            return entry[0]
    try:
        client = client_factory(center)
        client.login()
    except Exception as exc:
        raise BrowseError(f"ECM({center}) 접속에 실패했습니다: {exc}", 502) from exc
    with _CLIENT_LOCK:
        _CLIENTS[center] = (client, now)
    return client


def reset_clients():
    with _CLIENT_LOCK:
        _CLIENTS.clear()


def open_root(project_number, cert_date="", center_hint=""):
    """프로젝트 root 폴더를 센터 ECM 에서 찾는다. 반환: (center, folder{oid,name})."""
    errors = []
    for center in center_try_order(center_hint):
        try:
            client = get_client(center)
            folder = client.find_full_project_folder(project_number, cert_date, center)
        except BrowseError as exc:
            errors.append(f"{center}: {exc.message}")
            continue
        except Exception as exc:
            errors.append(f"{center}: {exc}")
            continue
        if folder and folder.get("oid"):
            return center, folder
    detail = "; ".join(errors) if errors else "해당 없음"
    raise BrowseError(f"ECM 에서 프로젝트 폴더를 찾지 못했습니다 ({detail})", 404)


# ---------------------------------------------------------------------------
# 이름 처리 / 정렬
# ---------------------------------------------------------------------------
def normalize_entry_name(name):
    text = unicodedata.normalize("NFC", str(name or "")).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _is_junk(normalized):
    if normalized.startswith(JUNK_PREFIXES):
        return True
    base = normalized.rstrip("/").rsplit("/", 1)[-1]
    return base.startswith(JUNK_BASENAME_PREFIXES)


def _natural_key(text):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(text))]


def is_zip_name(name):
    return str(name or "").lower().endswith(".zip")


def _basename(name):
    return PurePosixPath(normalize_entry_name(name).rstrip("/")).name or "download"


def _zip_max_bytes():
    return int(getattr(settings, "FOLDER_BROWSER_ZIP_MAX_MB", DEFAULT_ZIP_MAX_MB)) * 1024 * 1024


# ---------------------------------------------------------------------------
# 목록
# ---------------------------------------------------------------------------
def list_location(project_number, ref=None, *, center_hint="", cert_date="", sid=""):
    """위치(root / ECM 폴더 / zip 안 폴더) 한 곳의 항목 목록. sid 는 요청을 보낸 팝업의 세션 id(받기 취소 판단용)."""
    token = _current_sid.set(sid or "")
    try:
        return _list_location(project_number, ref, center_hint=center_hint, cert_date=cert_date)
    finally:
        _current_sid.reset(token)


def _list_location(project_number, ref=None, *, center_hint="", cert_date=""):
    if ref:
        payload = read_ref(ref, project_number)
    else:
        center, folder = open_root(project_number, cert_date, center_hint)
        payload = {"k": "folder", "c": center, "p": project_number, "oid": folder["oid"], "label": folder.get("name", "")}

    kind = payload.get("k")
    if kind == "folder":
        items = _list_ecm_folder(payload)
        if not ref:
            _maybe_prefetch(project_number, items)
    elif kind == "zip":
        items = _list_zip_level(payload)
    else:
        raise BrowseError("폴더나 zip 이 아닌 항목은 열 수 없습니다.", 400)
    return {
        "location": {"ref": make_ref(payload), "label": payload.get("label", ""), "kind": kind, "center": payload["c"]},
        "items": items,
    }


def _child_ref(payload, **changes):
    child = {key: payload[key] for key in ("c", "p")}
    child.update(changes)
    return make_ref(child)


def _list_ecm_folder(payload):
    client = get_client(payload["c"])
    try:
        contents = client.folder_contents(payload["oid"])
    except Exception as exc:
        raise BrowseError(f"ECM 폴더를 읽지 못했습니다: {exc}", 502) from exc

    items = []
    for folder in sorted(contents.get("folders") or [], key=lambda f: _natural_key(f.get("name", ""))):
        name = unicodedata.normalize("NFC", folder.get("name", ""))
        items.append({
            "type": "folder", "name": name, "size": None,
            "ref": _child_ref(payload, k="folder", oid=folder["oid"], label=name), "selectable": True, "downloadable": True,
        })
    for meta in sorted(contents.get("files") or [], key=lambda f: _natural_key(f.get("fileName", ""))):
        name = unicodedata.normalize("NFC", meta.get("fileName", ""))
        file_ref = _child_ref(payload, k="file", meta=_meta_to_token(meta))
        size = int(float(meta.get("fileSize") or 0))
        if is_zip_name(name):
            items.append({
                "type": "zip", "name": name, "size": size, "selectable": True, "downloadable": True,
                "ref": _child_ref(payload, k="zip", meta=_meta_to_token(meta), chain=[], dir="", label=name),
                "download_ref": file_ref,
            })
        else:
            items.append({
                "type": "file", "name": name, "size": size, "ref": file_ref, "selectable": True, "downloadable": True,
            })
    return items


@contextmanager
def open_zip_chunks(payload, *, budget=None):
    """payload(k=zip|zfile 의 meta/chain)가 가리키는 zip 의 바이트 조각 반복자. 중첩이면 안쪽 zip 의 조각이다.

    서버에 완성된 사본이 있으면 ECM 에 접속하지 않고 사본에서 읽는다. 없으면 ECM 에서 흘려받는다.
    """
    chain = list(payload.get("chain") or [])
    if len(chain) >= MAX_NESTED_ZIP_DEPTH:
        raise BrowseError("zip 안의 zip 은 3단계까지만 열 수 있습니다.", 400)
    budget = _zip_max_bytes() if budget is None else budget

    job = _complete_job(payload)
    if job is not None:
        with job.reading():
            path = job.data_path
            if chain:
                chunks = ecm_zip_stream.iter_file_entry_chunks(path, chain[0], chunk_size=STREAM_CHUNK_BYTES)
                for name in chain[1:]:
                    chunks = ecm_zip_stream.iter_entry_chunks(chunks, name, max_stream_bytes=budget, chunk_size=STREAM_CHUNK_BYTES)
            else:
                chunks = ecm_zip_stream.iter_file_chunks(path, chunk_size=STREAM_CHUNK_BYTES)
            yield chunks
        return

    client = get_client(payload["c"])
    try:
        response = client.blob_stream(_meta_from_token(payload["meta"]))
    except Exception as exc:
        raise BrowseError(f"ECM 파일을 열지 못했습니다: {exc}", 502) from exc
    try:
        chunks = response.iter_content(chunk_size=STREAM_CHUNK_BYTES)
        for name in chain:
            chunks = ecm_zip_stream.iter_entry_chunks(chunks, name, max_stream_bytes=budget, chunk_size=STREAM_CHUNK_BYTES)
        yield chunks
    finally:
        response.close()


# ---------------------------------------------------------------------------
# 임시 보관: 받으면서 목록 만들기 + 사본 저장
# ---------------------------------------------------------------------------
def _job_for(payload):
    if not zc.enabled():
        return None
    return zip_cache.lookup(payload["c"], _meta_from_token(payload["meta"]))


def _complete_job(payload):
    job = _job_for(payload)
    if job is not None and job.state == zc.COMPLETE and job.data_path.exists():
        return job
    return None


def _ensure_spool(payload, budget=None, priority=2):
    """이 zip(ECM 파일)의 받기 작업을 시작하거나 진행 중인 것을 돌려준다. 임시 보관을 쓸 수 없으면 None."""
    if not zc.enabled() or payload.get("chain"):
        return None
    budget = _zip_max_bytes() if budget is None else budget
    return zip_cache.ensure(
        payload["c"], _meta_from_token(payload["meta"]), _spool_zip, budget,
        sid=_current_sid.get() or None, priority=priority,
    )


def _spool_zip(job):
    """(백그라운드) ECM 에서 zip 을 받아 사본 파일에 그대로 쓴다.

    받는 동안 압축을 풀거나 헤더를 해석하지 않는다. 목록은 다 받은 뒤 중앙 디렉터리에서 한 번에 읽는다
    (_job_listing). 전송 중에 항목을 풀면 CPU 를 독점하는 스레드가 생겨, 같은 프로세스의 다른 요청(상세 조회 등)이
    GIL 을 기다리며 크게 느려지기 때문이다. 파일 쓰기·네트워크 읽기는 GIL 을 놓으므로 이 방식은 서버를 거의 방해하지 않는다.
    """
    client = get_client(job.center)
    response = client.blob_stream(job.meta)
    try:
        with open(job.part_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=STREAM_CHUNK_BYTES):
                if job.cancelled:
                    raise zc.ZipSpoolCancelled()
                handle.write(chunk)
                with job.cond:
                    job.written += len(chunk)
                    job.cond.notify_all()
                if job.written > job.budget:
                    raise ecm_zip_stream.ZipStreamBudgetExceeded(
                        f"전송 한도 {job.budget:,} bytes 를 넘겨 중단합니다."
                    )
    finally:
        response.close()

    if job.written != job.total:
        raise EOFError(f"받은 크기({job.written:,})가 ECM 의 파일 크기({job.total:,})와 다릅니다.")
    job.listing = ecm_zip_stream.list_entries_from_file(job.part_path)
    _publish_spool(job)


def _publish_spool(job):
    """완성된 .part 를 .zip 으로 확정한다. 다른 스레드가 읽는 중이라 이름을 못 바꾸면 .part 를 그대로 쓴다."""
    for _ in range(10):
        try:
            os.replace(job.part_path, job.final_path)
            return
        except PermissionError:
            time.sleep(0.2)
        except FileNotFoundError:
            return
    logger.info("zip cache: kept .part as the data file for %s", job.meta.get("fileName"))


def _job_listing(job):
    if job.listing is None:
        with job.reading():
            job.listing = ecm_zip_stream.list_entries_from_file(job.data_path)
    return job.listing


def _spooled_entries(payload, budget):
    """임시 보관 작업으로 최상위 zip 의 목록을 얻는다. 보관을 쓸 수 없으면 None(호출자가 ECM 에서 직접 읽는다)."""
    job = _ensure_spool(payload, budget, priority=0)  # 사용자가 직접 연 zip 은 미리 받기보다 먼저 받는다
    if job is None:
        return None
    wait = float(getattr(settings, "FOLDER_BROWSER_LIST_WAIT_SECONDS", DEFAULT_LIST_WAIT_SECONDS))
    state = job.wait(wait)
    if state == zc.RUNNING:
        raise BrowseError("zip 을 읽는 데 시간이 오래 걸립니다. 서버가 계속 받고 있으니 잠시 뒤 다시 열어 주세요.", 504)
    if state == zc.CANCELED:
        raise BrowseError("zip 받기가 취소되었습니다. 다시 열어 주세요.", 409)
    if state == zc.FAILED:
        raise job.error
    return _job_listing(job)


def zip_progress(project_number, ref):
    """zip 읽기 진행 상황(화면 진행률 막대용). 최상위 zip 만 추적한다."""
    payload = read_ref(ref, project_number)
    if payload.get("k") != "zip" or payload.get("chain"):
        return {"state": "none"}
    job = _job_for(payload)
    if job is None:
        return {"state": "none"}
    return job.progress()


def _maybe_prefetch(project_number, items):
    """팝업을 열 때(root 목록) root 바로 아래의 가장 큰 zip 1개를 백그라운드로 미리 받기 시작한다."""
    if not zc.enabled() or not getattr(settings, "FOLDER_BROWSER_PREFETCH", True):
        return
    minimum = int(float(getattr(settings, "FOLDER_BROWSER_PREFETCH_MIN_MB", DEFAULT_PREFETCH_MIN_MB)) * 1024 * 1024)
    zips = [item for item in items if item["type"] == "zip" and minimum <= int(item.get("size") or 0) <= _zip_max_bytes()]
    if not zips:
        return
    biggest = max(zips, key=lambda item: item["size"])
    try:
        _ensure_spool(read_ref(biggest["ref"], project_number), priority=1)
    except Exception:  # 미리 받기는 덤이다. 실패해도 목록은 정상으로 보여준다.
        logger.info("folder browser: prefetch failed", exc_info=True)


def _zip_cache_key(payload):
    meta = payload["meta"]
    raw = f"{payload['c']}|{meta['s']}|{meta['z']}|{'/'.join(payload.get('chain') or [])}"
    return "gscert:zip-list:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _wrap_zip_errors(exc):
    if isinstance(exc, BrowseError):
        return exc
    if isinstance(exc, ecm_zip_stream.ZipStreamBudgetExceeded):
        return BrowseError(f"zip 이 너무 커서 열 수 없습니다 ({exc})", 413)
    if isinstance(exc, KeyError):
        return BrowseError("zip 안에서 항목을 찾지 못했습니다.", 404)
    if isinstance(exc, (EOFError, zipfile.BadZipFile)):
        return BrowseError("zip 이 손상되었거나 중간에 끊겼습니다.", 502)
    if isinstance(exc, ecm_zip_stream.ZipStreamUnsupported):
        return BrowseError(f"이 zip 은 열 수 없습니다: {exc}", 422)
    return BrowseError(f"zip 을 읽지 못했습니다: {exc}", 502)


def zip_entries(payload):
    """zip(또는 중첩 zip) 안의 전체 항목 목록. 캐시에 있으면 다시 받지 않는다."""
    key = _zip_cache_key(payload)
    cached = cache.get(key)
    if cached is not None:
        return cached

    budget = _zip_max_bytes()
    try:
        entries = None
        if not payload.get("chain"):
            entries = _spooled_entries(payload, budget)
        if entries is None:
            try:
                with open_zip_chunks(payload, budget=budget) as chunks:
                    entries, _read = ecm_zip_stream.list_entries(chunks, max_stream_bytes=budget)
            except ecm_zip_stream.ZipStreamUnsupported:
                entries = _list_via_tempfile(payload, budget)
    except Exception as exc:
        raise _wrap_zip_errors(exc) from exc

    cache.set(key, entries, int(getattr(settings, "FOLDER_BROWSER_LIST_CACHE_SECONDS", DEFAULT_LIST_CACHE_SECONDS)))
    return entries


def _list_via_tempfile(payload, budget):
    with open_zip_chunks(payload, budget=budget) as chunks:
        path = ecm_zip_stream.spool_to_tempfile(chunks, max_stream_bytes=budget)
    try:
        return ecm_zip_stream.list_entries_from_file(path)
    finally:
        _remove(path)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def build_level(entries, directory=""):
    """전체 항목 목록에서 directory(끝이 "/" 인 경로 또는 "") 바로 아래의 (폴더 이름들, 파일 항목들)."""
    dirs = set()
    files = []
    for entry in entries:
        normalized = normalize_entry_name(entry["name"])
        if not normalized or _is_junk(normalized) or not normalized.startswith(directory):
            continue
        rest = normalized[len(directory):]
        if not rest:
            continue
        stripped = rest.rstrip("/")
        if "/" in stripped:
            dirs.add(stripped.split("/", 1)[0])
        elif entry.get("is_dir") or rest.endswith("/"):
            dirs.add(stripped)
        else:
            files.append((stripped, entry))
    return sorted(dirs, key=_natural_key), sorted(files, key=lambda pair: _natural_key(pair[0]))


def _list_zip_level(payload):
    entries = zip_entries(payload)
    directory = payload.get("dir") or ""
    dirs, files = build_level(entries, directory)
    items = []
    for name in dirs:
        items.append({
            "type": "zipdir", "name": name, "size": None, "selectable": True, "downloadable": True,
            "ref": _child_ref(payload, k="zip", meta=payload["meta"], chain=payload.get("chain") or [],
                              dir=f"{directory}{name}/", label=name),
        })
    for name, entry in files:
        raw_name = entry["name"]
        encrypted = bool(entry.get("encrypted"))
        file_ref = _child_ref(payload, k="zfile", meta=payload["meta"], chain=payload.get("chain") or [], name=raw_name)
        base = {"name": name, "size": entry.get("size"), "encrypted": encrypted,
                "selectable": not encrypted, "downloadable": not encrypted}
        if is_zip_name(name) and not encrypted and len(payload.get("chain") or []) + 1 < MAX_NESTED_ZIP_DEPTH:
            items.append({
                **base, "type": "zip", "download_ref": file_ref,
                "ref": _child_ref(payload, k="zip", meta=payload["meta"], chain=list(payload.get("chain") or []) + [raw_name],
                                  dir="", label=name),
            })
        else:
            items.append({**base, "type": "zipfile", "ref": file_ref})
    return items


# ---------------------------------------------------------------------------
# 다운로드: 항목 1개
# ---------------------------------------------------------------------------
def describe_single_download(project_number, ref):
    """ref 가 파일 하나(ECM 파일 / zip 안의 파일)면 (파일 이름, 조각 생성기)를, 아니면 None 을 돌려준다."""
    payload = read_ref(ref, project_number)
    kind = payload.get("k")
    if kind == "file":
        return _basename(payload["meta"]["n"]), iter_ecm_file(payload)
    if kind == "zfile":
        return _basename(payload["name"]), iter_zip_entry(payload)
    return None


def iter_ecm_file(payload):
    client = get_client(payload["c"])
    try:
        response = client.blob_stream(_meta_from_token(payload["meta"]))
    except Exception as exc:
        raise BrowseError(f"ECM 파일을 열지 못했습니다: {exc}", 502) from exc
    try:
        yield from response.iter_content(chunk_size=STREAM_CHUNK_BYTES)
    finally:
        response.close()


def _serve_from_spool(payload):
    """서버 사본에서 항목을 보낸다. 보냈으면 True, 사본이 없거나 아직 못 꺼내면 False(호출자가 ECM 에서 직접 보낸다)."""
    name = payload["name"]
    job = _job_for(payload)
    if job is None:
        _ensure_spool(payload)  # 이번 요청은 ECM 에서 바로 보내고, 다음 요청을 위해 사본을 만들어 둔다
        return False
    if job.state == zc.RUNNING:
        if job.total and job.written / job.total >= NEAR_DONE_FRACTION:
            job.wait(NEAR_DONE_WAIT_SECONDS)  # 거의 다 받았으면 ECM 에서 다시 받지 않고 끝나기를 기다린다
    if job.state == zc.COMPLETE and job.data_path.exists():
        with job.reading():
            yield from ecm_zip_stream.iter_file_entry_chunks(job.data_path, name, chunk_size=STREAM_CHUNK_BYTES)
        return True
    return False


def iter_zip_entry(payload):
    """zip 안의 파일 하나의 풀린 내용. 서버 사본이 있으면 거기서, 없으면 zip 을 흘려받다가 그 항목만 보낸다."""
    budget = _zip_max_bytes()
    try:
        if not payload.get("chain"):
            served = yield from _serve_from_spool(payload)
            if served:
                return
        try:
            with open_zip_chunks(payload, budget=budget) as chunks:
                yield from ecm_zip_stream.iter_entry_chunks(
                    chunks, payload["name"], max_stream_bytes=budget, chunk_size=STREAM_CHUNK_BYTES,
                )
            return
        except ecm_zip_stream.ZipStreamUnsupported:
            pass
        with open_zip_chunks(payload, budget=budget) as chunks:
            path = ecm_zip_stream.spool_to_tempfile(chunks, max_stream_bytes=budget)
        try:
            yield from ecm_zip_stream.iter_file_entry_chunks(path, payload["name"], chunk_size=STREAM_CHUNK_BYTES)
        finally:
            _remove(path)
    except Exception as exc:
        raise _wrap_zip_errors(exc) from exc


# ---------------------------------------------------------------------------
# 다운로드: 여러 항목 / 폴더 -> zip
# ---------------------------------------------------------------------------
def _write_entry(zf, sink, arcname, chunks, seen):
    """chunks 를 zip 항목 하나로 쓴다.

    첫 조각을 먼저 받아 본 뒤에 항목을 만들어, 열지 못한 파일이 빈 항목으로 남거나 이름만 차지하지 않게 한다.
    같은 이름이 이미 있으면 `(2)` 를 붙인다(seen).
    """
    chunks = iter(chunks)
    first = next(chunks, b"")
    info = zipfile.ZipInfo(_unique_arcname(arcname, seen))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zf.open(info, "w", force_zip64=True) as handle:
        yield from sink.drain()
        if first:
            handle.write(first)
            yield from sink.drain()
        for chunk in chunks:
            handle.write(chunk)
            yield from sink.drain()
    yield from sink.drain()


def plan_selection(project_number, refs):
    """선택한 ref 들을 (ECM 파일 작업, ECM 폴더 작업, zip 별 작업 묶음)으로 나눈다."""
    max_selection = int(getattr(settings, "FOLDER_BROWSER_MAX_SELECTION", DEFAULT_MAX_SELECTION))
    refs = [ref for ref in refs if ref]
    if not refs:
        raise BrowseError("선택된 항목이 없습니다.", 400)
    if len(refs) > max_selection:
        raise BrowseError(f"한 번에 최대 {max_selection}개 항목까지 선택할 수 있습니다. (선택 {len(refs)}개)", 400)

    files, folders, groups = [], [], {}
    for ref in refs:
        payload = read_ref(ref, project_number)
        kind = payload.get("k")
        if kind == "file":
            files.append(payload)
        elif kind == "folder":
            folders.append(payload)
        elif kind in ("zip", "zfile"):
            key = (payload["c"], payload["meta"]["s"], tuple(payload.get("chain") or []))
            group = groups.setdefault(key, {"payload": payload, "files": {}, "prefixes": []})
            if kind == "zfile":
                group["files"][payload["name"]] = _basename(payload["name"])
            else:
                directory = payload.get("dir") or ""
                base = _safe_zip_part(payload.get("label") or "zip") if not directory else _safe_zip_part(directory.rstrip("/").rsplit("/", 1)[-1])
                if not directory and is_zip_name(base):
                    base = base[:-4]
                group["prefixes"].append((directory, base))
        else:
            raise BrowseError("다운로드할 수 없는 항목입니다.", 400)
    return files, folders, groups


def iter_selection_zip(project_number, refs):
    """선택한 항목들을 하나의 zip 으로 스트리밍한다. 항목별 실패는 전체를 멈추지 않고 `_다운로드_오류.txt` 에 남긴다."""
    files, folders, groups = plan_selection(project_number, refs)
    max_files = int(getattr(settings, "FOLDER_BROWSER_MAX_FILES", DEFAULT_MAX_FILES_PER_DOWNLOAD))

    sink = _StreamingZipSink()
    seen = {}
    errors = []
    written = 0

    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for payload in files:
            name = _basename(payload["meta"]["n"])
            try:
                yield from _write_entry(zf, sink, _safe_zip_part(name), iter_ecm_file(payload), seen)
                written += 1
            except Exception as exc:
                errors.append(f"{name}: {_error_text(exc)}")

        for payload in folders:
            label = _safe_zip_part(payload.get("label") or "folder")
            try:
                client = get_client(payload["c"])
                for rel, meta in client.walk_files(payload["oid"]):
                    if written >= max_files:
                        errors.append(f"{label}: 파일이 {max_files}개를 넘어 나머지는 건너뜁니다.")
                        break
                    parts = [label] + [_safe_zip_part(part) for part in rel] + [_safe_zip_part(meta.get("fileName", "download"))]
                    file_payload = {"c": payload["c"], "meta": _meta_to_token(meta)}
                    try:
                        yield from _write_entry(zf, sink, "/".join(parts), iter_ecm_file(file_payload), seen)
                        written += 1
                    except Exception as exc:
                        errors.append(f"{'/'.join(parts)}: {_error_text(exc)}")
            except Exception as exc:
                errors.append(f"{label}: {_error_text(exc)}")

        for group in groups.values():
            group_name = group["payload"]["meta"]["n"]
            state = {"done": set()}
            try:
                try:
                    for item in _iter_zip_group(zf, sink, group, seen, errors, max_files - written, state):
                        written += 1
                        yield from item
                except ecm_zip_stream.ZipStreamUnsupported:
                    # 순차 해석이 불가능한 zip: 임시 파일로 받아 아직 쓰지 않은 항목만 이어서 쓴다.
                    for item in _iter_zip_group_via_tempfile(zf, sink, group, seen, errors, max_files - written, state):
                        written += 1
                        yield from item
                for name in sorted(set(group["files"]) - state["done"]):
                    errors.append(f"{group_name}: {name} - zip 안에서 찾지 못했습니다.")
            except Exception as exc:
                errors.append(f"{group_name}: {_error_text(exc)}")

        if errors:
            zf.writestr("_다운로드_오류.txt", ("\n".join(errors) + "\n").encode("utf-8-sig"))
            yield from sink.drain()
    yield from sink.drain()


def _error_text(exc):
    return exc.message if isinstance(exc, BrowseError) else str(exc)


def _group_matcher(group):
    """zip 항목 이름 -> 결과 zip 안에서 쓸 경로(선택에 해당하지 않으면 None)."""
    wanted_files = dict(group["files"])   # 원래 이름 -> 보낼 이름
    prefixes = list(group["prefixes"])    # (정규화된 폴더 경로, 결과 zip 안에서 쓸 폴더 이름)

    def match(name, is_dir):
        if name in wanted_files:
            return wanted_files[name]
        normalized = normalize_entry_name(name)
        if is_dir or _is_junk(normalized):
            return None
        for directory, base in prefixes:
            if normalized.startswith(directory):
                rel = normalized[len(directory):]
                if rel:
                    return "/".join([base] + [_safe_zip_part(part) for part in rel.split("/")])
        return None

    return match, bool(prefixes)


def _tracked(write, state, name):
    yield from write
    state["done"].add(name)


def _iter_zip_group(zf, sink, group, seen, errors, remaining, state):
    """같은 zip 에서 고른 항목을 한 번만 받으며 꺼낸다. 항목 하나를 쓸 때마다 그 쓰기용 생성기를 내보낸다."""
    match, has_prefixes = _group_matcher(group)
    budget = _zip_max_bytes()
    with open_zip_chunks(group["payload"], budget=budget) as chunks:
        for entry in ecm_zip_stream.iter_zip_entries(chunks, max_stream_bytes=budget):
            arcname = match(entry.name, entry.is_dir)
            if arcname is None:
                continue
            if entry.encrypted:
                errors.append(f"{entry.name}: 암호화된 항목이라 건너뜁니다.")
                state["done"].add(entry.name)
                continue
            if remaining <= 0:
                errors.append("파일이 너무 많아 나머지는 건너뜁니다.")
                return
            remaining -= 1
            yield _tracked(_write_entry(zf, sink, arcname, entry.iter_data(STREAM_CHUNK_BYTES), seen), state, entry.name)
            if not has_prefixes and set(group["files"]) <= state["done"]:
                return  # 고른 파일을 모두 찾았으면 나머지 zip 은 읽지 않는다


def _iter_zip_group_via_tempfile(zf, sink, group, seen, errors, remaining, state):
    """대체 경로: zip 을 임시 파일로 받아 아직 쓰지 않은(state["done"] 에 없는) 항목만 쓴다."""
    match, _has_prefixes = _group_matcher(group)
    budget = _zip_max_bytes()
    with open_zip_chunks(group["payload"], budget=budget) as chunks:
        path = ecm_zip_stream.spool_to_tempfile(chunks, max_stream_bytes=budget)
    try:
        with zipfile.ZipFile(path) as source:
            for info in source.infolist():
                name = info.filename if info.flag_bits & 0x800 else ecm_zip_stream._cp949_from_cp437(info.filename)
                if name in state["done"]:
                    continue
                arcname = match(name, info.is_dir())
                if arcname is None:
                    continue
                if info.flag_bits & 0x1:
                    errors.append(f"{name}: 암호화된 항목이라 건너뜁니다.")
                    state["done"].add(name)
                    continue
                if remaining <= 0:
                    errors.append("파일이 너무 많아 나머지는 건너뜁니다.")
                    return

                remaining -= 1

                def read_chunks(info=info):
                    with source.open(info) as handle:
                        while True:
                            data = handle.read(STREAM_CHUNK_BYTES)
                            if not data:
                                return
                            yield data

                yield _tracked(_write_entry(zf, sink, arcname, read_chunks(), seen), state, name)
    finally:
        _remove(path)
