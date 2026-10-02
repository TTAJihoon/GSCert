"""KOLAS 페이지 '결과서 다운로드': 선택한 프로젝트의 시험성적서(Word/PDF)를 ECM 에서 받아 zip 으로 스트리밍.

경로: 연도 폴더 트리 → 프로젝트번호 폴더(ecm_http_client.find_full_project_folder 재사용) →
`시험 > 종료` 폴더(점검 규칙 8번의 folder_keyword_chain 과 동일)에서 파일명에 '시험성적서'가 들어간
Word/PDF 를 찾는다. `시험 > 종료` 에서 못 찾으면 프로젝트 폴더 전체를 훑는 폴백(점검 규칙의
folder_fallback_search_all 과 동일 취지).

프로젝트 폴더에 시험성적서 파일이 직접 없고 프로젝트 전체가 zip 하나로 올라가 있는 경우에는, 그 zip 을
디스크에 저장하지 않고 스트리밍으로 흘려받으며(ecm_zip_stream) 안의 시험성적서 Word/PDF 만 꺼낸다.
ECM 은 Range 를 지원하지 않아 전송은 zip 크기만큼 일어나지만(194->ECM 약 41MB/s) 디스크에는 남지 않는다.

프로젝트 폴더(와 그 안의 zip)에 시험성적서가 업로드되어 있지 않으면, 분당 ECM 의 인증위원회 트리
(`{연도} 시험서비스 > GS인증심의위원회 > 회차 > 인증일자 > 시험번호`)에 센터와 무관하게 모여 있는 **익명 시험성적서
(Word)** 로 대체한다. 이 파일들은 결과 zip 의 `익명/` 폴더에 담기며, **서버에 저장하지 않는다**: 요청할 때마다
본래 센터 ECM 에서 먼저 찾아보고, 그래도 없으면 다시 익명본을 받는다(각 센터 ECM 에서 찾은 최종본만 저장).

zip 구조:  word/<파일>, pdf/<파일>, 익명/<파일>, _다운로드_결과.txt(성공/누락 요약)

한 번 받은 프로젝트는 서버 저장소(kolas_report_cache)에 보관했다가 다음 요청에 그대로 전달한다.
"""

import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath

from django.conf import settings

from main.views.review import kolas_report_cache as report_cache
from main.views.review import ecm_zip_stream
from main.views.review import kolas_report_task as task_progress
from main.views.review.ecm_http_client import DestinyECM, build_client
from main.views.testing.history_download import (
    _safe_zip_part,
    _StreamingZipSink,
    _unique_arcname,
)

logger = logging.getLogger(__name__)

REPORT_KEYWORD = DestinyECM.REPORT_DOC_KEYWORD
WORD_EXTENSIONS = DestinyECM.REPORT_DOC_EXTS
PDF_EXTENSIONS = (".pdf",)
FOLDER_CHAIN = ("시험", "종료")
CENTER_FALLBACK_ORDER = ("bundang", "sangam", "yeongnam")
REAL_CENTERS = set(CENTER_FALLBACK_ORDER)
SUMMARY_NAME = "_다운로드_결과.txt"
SOURCE_CACHE = "서버 저장본"
SOURCE_ECM = "ECM에서 새로 받음"
SOURCE_ZIP = "ECM zip 안에서 추출"
SOURCE_ANON = "분당 ECM 익명본으로 대체(프로젝트 폴더에 시험성적서 없음, 서버에 저장 안 함)"
ZIP_DIRS = {"word": "word", "pdf": "pdf", "anon": "익명"}  # 결과 zip 안의 폴더
ANON_CENTER = "bundang"
ANON_KEYWORD = "익명"
DEFAULT_ZIP_SCAN_MAX_MB = 1024
STREAM_CHUNK_BYTES = 1024 * 1024
# 시험성적서가 들어 있을 가능성이 낮은 부속 자료 zip(원시데이터·캡처·홍보 등). 다른 zip 에서 못 찾았을 때만 연다.
AUX_ZIP_RE = re.compile(r"rawdata|raw[_ -]?data|성능|홍보|캡[쳐처]|화면|스크린|이미지|image|결함|defect", re.I)


def classify_report_file(file_name):
    """'시험성적서' 원본 문서면 'word' / 'pdf', 아니면 None. 이름에 '익명' 이 든 익명본은 원본이 아니므로 제외한다
    (분당 프로젝트 폴더에는 원본과 `- 익명.docx` 가 함께 있다. 익명본은 따로 select_anonymous_report_files 로 다룬다)."""
    if ANON_KEYWORD in unicodedata.normalize("NFC", str(file_name or "")):
        return None
    return _classify_any_report(file_name)


def is_temp_file_name(file_name):
    """Office 소유자(잠금) 파일 `~$...docx`, Word 임시 `~WRL*.tmp`, macOS `._*`, LibreOffice `.~lock.*` 같은 임시 파일.

    압축 폴더 안에 문서를 연 채로 올린 경우 이런 파일이 `~$GS-B-25-0110 시험성적서 v1.0.docx`(162바이트) 처럼
    시험성적서와 같은 이름으로 들어 있다. 문서가 아니므로 시험성적서로 보면 안 된다.
    """
    base = str(file_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    return base.startswith(("~", "._", ".~lock"))


def _classify_any_report(file_name):
    name = unicodedata.normalize("NFC", str(file_name or ""))
    if is_temp_file_name(name):
        return None
    lower = name.lower()
    if REPORT_KEYWORD not in name:
        return None
    if lower.endswith(WORD_EXTENSIONS):
        return "word"
    if lower.endswith(PDF_EXTENSIONS):
        return "pdf"
    return None


def select_report_files(files):
    """ECM 파일 메타 목록에서 시험성적서 Word/PDF 만 [(kind, meta)] 로."""
    selected = []
    for meta in files or []:
        kind = classify_report_file(meta.get("fileName"))
        if kind:
            selected.append((kind, meta))
    return selected


def find_report_files(client, project_folder_oid, zips=None):
    """프로젝트 폴더에서 시험성적서 파일을 찾는다. 반환: [(kind, meta)].

    zips 리스트를 넘기면, 프로젝트 폴더 전체를 훑는 폴백 단계에서 만난 .zip 파일을 [(상대경로, meta)] 로 모아 준다.
    """
    # 1) 시험 > 종료 폴더 (점검 규칙과 동일한 폴더 체인)
    first, second = FOLDER_CHAIN
    for level1 in client.children(project_folder_oid):
        if first not in str(level1.get("name", "")):
            continue
        level1_oid = client.oid(level1)
        if not level1_oid:
            continue
        for level2 in client.children(level1_oid):
            if second not in str(level2.get("name", "")):
                continue
            level2_oid = client.oid(level2)
            if not level2_oid:
                continue
            found = select_report_files(client.files(level2_oid))
            if found:
                return found

    # 2) 폴백: 프로젝트 폴더 전체
    found = []
    for rel, meta in client.walk_files(project_folder_oid):
        kind = classify_report_file(meta.get("fileName"))
        if kind:
            found.append((kind, meta))
        elif zips is not None and str(meta.get("fileName", "")).lower().endswith(".zip"):
            zips.append(("/".join(rel), meta))
    return found


def center_try_order(project_center):
    order = []
    if project_center in REAL_CENTERS:
        order.append(project_center)
    for center in CENTER_FALLBACK_ORDER:
        if center not in order:
            order.append(center)
    return order


class _ClientPool:
    """센터별 ECM 클라이언트를 요청 한 번 동안 재사용(로그인 1회). 실패한 센터는 기억해 재시도하지 않는다."""

    def __init__(self, factory=build_client):
        self._factory = factory
        self._clients = {}
        self._errors = {}

    def get(self, center):
        if center in self._errors:
            raise self._errors[center]
        client = self._clients.get(center)
        if client is None:
            try:
                client = self._factory(center)
                client.login()
            except Exception as exc:
                self._errors[center] = exc
                raise
            self._clients[center] = client
        return client


def _zip_size(meta):
    return int(float(meta.get("fileSize") or 0))


def order_zip_candidates(zips, project_number):
    """zip 후보를 열어 볼 순서로 정렬한다: (부속 자료 아님) -> 최상위 -> 프로젝트번호가 이름에 있음 -> 큰 것."""
    def key(item):
        rel, meta = item
        name = str(meta.get("fileName", ""))
        aux = bool(AUX_ZIP_RE.search(name)) or bool(AUX_ZIP_RE.search(rel))
        return (aux, 0 if not rel else 1, 0 if project_number in name else 1, -_zip_size(meta))

    return sorted(zips, key=key)


def extract_reports_from_zips(client, zips, project_number, *, max_total_bytes=None):
    """프로젝트 폴더의 zip 들을 스트리밍으로 훑어 시험성적서 Word/PDF 를 꺼낸다.

    반환: ([(kind, 파일명, bytes, zip 이름)], [메모]). 시험성적서를 찾은 첫 zip 에서 멈춘다.
    부속 자료로 보이는 zip(rawdata 등)은 다른 zip 에서 못 찾았을 때만 연다.
    """
    if max_total_bytes is None:
        max_total_bytes = int(getattr(settings, "KOLAS_ZIP_SCAN_MAX_MB", DEFAULT_ZIP_SCAN_MAX_MB)) * 1024 * 1024
    notes = []
    spent = 0

    def want(name):
        return bool(classify_report_file(PurePosixPath(str(name).replace("\\", "/")).name))

    for rel, meta in order_zip_candidates(zips, project_number):
        zip_name = meta.get("fileName", "")
        budget = max_total_bytes - spent
        if budget <= 0:
            notes.append(f"zip 탐색 한도({max_total_bytes // 1024 // 1024}MB) 초과로 '{zip_name}' 등 나머지는 열지 않음")
            break
        try:
            result = _scan_zip(client, meta, want, budget)
        except ecm_zip_stream.ZipStreamBudgetExceeded:
            spent = max_total_bytes
            notes.append(f"'{zip_name}': 탐색 한도 초과")
            continue
        except Exception as exc:
            notes.append(f"'{zip_name}': zip 읽기 실패 - {exc}")
            continue
        spent += result.bytes_read
        for name, reason in result.skipped:
            notes.append(f"'{zip_name}' 안의 '{name}': {reason}")
        entries = []
        for name, data in result.files:
            base = unicodedata.normalize("NFC", PurePosixPath(name.replace("\\", "/")).name)
            entries.append((classify_report_file(base), base, data, zip_name))
        if entries:
            return entries, notes
        notes.append(f"'{zip_name}' ({result.entries_seen}개 항목) 안에 시험성적서 Word/PDF 없음")
    return [], notes


def _scan_zip(client, meta, want, budget):
    """zip 1개를 스트리밍으로 해석한다. 순차 해석이 불가능한 형식이면 임시 파일 방식으로 대체한다."""
    response = client.blob_stream(meta)
    try:
        return ecm_zip_stream.extract_matching(
            response.iter_content(chunk_size=STREAM_CHUNK_BYTES), want, max_stream_bytes=budget,
        )
    except (ecm_zip_stream.ZipStreamUnsupported, EOFError) as exc:
        logger.info("KOLAS zip streaming parse unsupported (%s) - falling back to temp file", exc)
    finally:
        response.close()

    response = client.blob_stream(meta)
    try:
        return ecm_zip_stream.extract_via_tempfile(
            response.iter_content(chunk_size=STREAM_CHUNK_BYTES), want, max_stream_bytes=budget,
        )
    finally:
        response.close()


@dataclass
class Located:
    client: object
    center: str
    folder_name: str
    files: list = field(default_factory=list)        # ECM 에 직접 있는 시험성적서 [(kind, meta)]
    zip_entries: list = field(default_factory=list)  # zip 안에서 꺼낸 시험성적서 [(kind, 파일명, bytes, zip 이름)]
    notes: list = field(default_factory=list)
    anonymous: bool = False                          # 분당 ECM 익명본으로 대체한 결과인지


def locate_project_reports(pool, project):
    """프로젝트의 시험성적서를 찾는다. 반환: Located (직접 있는 파일 또는 zip 에서 꺼낸 파일).

    못 찾으면 RuntimeError(원인 문자열).
    """
    test_no = project["project_number"]
    cert_date = project.get("cert_date_full") or ""
    errors = []
    folder_seen = False
    for center in center_try_order(project.get("center_code")):
        try:
            client = pool.get(center)
            folder = client.find_full_project_folder(test_no, cert_date, center)
        except Exception as exc:  # 자격증명 없음/네트워크/로그인 실패 -> 다음 센터
            errors.append(f"{center}: {exc}")
            continue
        if not folder or not folder.get("oid"):
            continue
        folder_seen = True
        zips = []
        files = find_report_files(client, folder["oid"], zips)
        folder_name = folder.get("name", "")
        if files:
            return Located(client, center, folder_name, files=files)
        if zips:
            entries, notes = extract_reports_from_zips(client, zips, test_no)
            if entries:
                return Located(client, center, folder_name, zip_entries=entries, notes=notes)
            errors.append(
                f"{center}: '{folder_name}' 폴더에 시험성적서 Word/PDF 없음, zip {len(zips)}개 확인 - " + " / ".join(notes)
            )
        else:
            errors.append(f"{center}: '{folder_name}' 폴더에 시험성적서 Word/PDF 없음")
    if folder_seen:
        raise RuntimeError("프로젝트 폴더는 찾았으나 시험성적서 파일이 없습니다 (" + "; ".join(errors) + ")")
    detail = "; ".join(errors) if errors else "해당 없음"
    raise RuntimeError(f"ECM 에서 프로젝트 폴더를 찾지 못했습니다 ({detail})")


def select_anonymous_report_files(metas):
    """분당 ECM 파일 목록에서 익명 시험성적서(Word)만 [meta] 로. 익명 문서는 항상 Word 라서 PDF 는 대상이 아니다."""
    selected = []
    seen = set()
    for meta in metas or []:
        name = unicodedata.normalize("NFC", str(meta.get("fileName") or ""))
        if ANON_KEYWORD not in name or _classify_any_report(name) != "word":
            continue
        key = meta.get("storageFileID") or name
        if key in seen:
            continue
        seen.add(key)
        selected.append(meta)
    return selected


def find_anonymous_report_files(pool, project):
    """분당 ECM 에서 프로젝트의 익명 시험성적서를 찾는다. 반환: (client, 위치 설명, [meta]).

    1) 인증위원회 트리 `{연도} 시험서비스 > GS인증심의위원회 > 회차 > 인증일자(yyyymmdd) > 시험번호` -
       센터와 무관하게 모든 프로젝트의 익명본이 있다(인증위원회 개최일 필요).
    2) 보조: 분당 프로젝트 폴더(`4.시험/라.종료`)에 있는 익명본(분당 프로젝트).
    못 찾으면 RuntimeError(원인).
    """
    number = project["project_number"]
    cert_date = project.get("cert_date_full") or ""
    try:
        client = pool.get(ANON_CENTER)
    except Exception as exc:
        raise RuntimeError(f"분당 ECM 접속 실패: {exc}") from exc

    tried = []
    if cert_date:
        try:
            folder = client.find_committee_test_folder(number, cert_date)
            if folder:
                metas = select_anonymous_report_files(m for _rel, m in client.walk_files(folder["oid"]))
                if metas:
                    return client, f"인증위원회/{folder.get('name', '')}", metas
                tried.append(f"인증위원회 폴더 '{folder.get('name', '')}' 에 익명 시험성적서 Word 없음")
            else:
                tried.append("인증위원회 트리에 시험번호 폴더 없음")
        except Exception as exc:
            tried.append(f"인증위원회 트리 조회 실패: {exc}")
    else:
        tried.append("인증위원회 개최일을 몰라 인증위원회 트리를 조회하지 못함")

    try:
        folder = client.find_full_project_folder(number, cert_date, ANON_CENTER)
        if folder and folder.get("oid"):
            metas = select_anonymous_report_files(m for _rel, m in client.walk_files(folder["oid"]))
            if metas:
                return client, f"분당 프로젝트 폴더/{folder.get('name', '')}", metas
            tried.append("분당 프로젝트 폴더에 익명 시험성적서 Word 없음")
        else:
            tried.append("분당 프로젝트 폴더 없음")
    except Exception as exc:
        tried.append(f"분당 프로젝트 폴더 조회 실패: {exc}")
    raise RuntimeError("분당 ECM 에서 익명 시험성적서를 찾지 못했습니다 (" + "; ".join(tried) + ")")


def iter_report_zip(projects, *, missing_numbers=(), pool=None, cache_dir=None, refresh=False, reporter=None):
    """projects: [{project_number, center_code, cert_date_full}] 의 시험성적서를 zip 으로 스트리밍.

    - 프로젝트마다 서버 저장소(kolas_report_cache)를 먼저 본다. 저장본이 있으면 ECM 에 접속하지 않고
      그대로 담고, 없으면 ECM 에서 받아 zip 에 담으면서 저장소에도 저장한다. refresh=True 면 저장본을
      무시하고 ECM 최신본으로 다시 받아 저장본을 교체한다.
    - zip 은 서버 디스크에 만들지 않고 파일 하나 처리할 때마다 조각을 흘려보낸다.
    - 프로젝트별 실패는 전체 중단 없이 _다운로드_결과.txt 에 기록한다. 그 로그에는 모든 요청 프로젝트에 대해
      word / pdf 시험성적서 유무가 한 줄씩 적힌다(build_summary 참고).
    - 프로젝트 폴더(와 zip)에 시험성적서가 없으면 분당 ECM 의 익명 시험성적서(Word)를 `익명/` 폴더로 대체한다.
      익명본은 서버에 저장하지 않으므로, 이후 요청에서도 본래 센터 ECM 을 먼저 다시 찾고 없을 때만 익명본을 받는다.
    - reporter(kolas_report_task.ReportTaskReporter)를 주면 프로젝트 단위로 진행률(0~100)을 기록한다. 전체 프로젝트
      수는 len(projects) + len(missing_numbers) 이고, 진행률은 '끝낸 프로젝트 수 + 현재 프로젝트의 단계 비율'이다.
    """
    from main.views.review.artifact_source import verify_downloaded_bytes

    pool = pool or _ClientPool()
    cache_dir = cache_dir if cache_dir is not None else report_cache.cache_root()
    sink = _StreamingZipSink()
    seen = {}
    succeeded = []  # (번호, [zip 경로...], 출처)
    failed = []     # (번호, 사유)
    rows = []       # 프로젝트별 word/pdf 유무 (build_summary 의 [프로젝트별 파일 유무])

    def progress_step(index, number, text, fraction):
        if reporter is not None:
            reporter.step(index, number, text, fraction)

    def progress_done(index, number, text="완료"):
        if reporter is not None:
            reporter.project_done(index, number, text)

    def add_entry(zf, number, kind, file_name, data):
        part = file_name if number in file_name else f"{number}_{file_name}"
        arcname = _unique_arcname(f"{ZIP_DIRS[kind]}/{_safe_zip_part(part)}", seen)
        info = zipfile.ZipInfo(arcname)
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, data)
        return arcname

    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index, project in enumerate(projects):
            number = project["project_number"]
            progress_step(index, number, "서버 저장소 확인 중", task_progress.STEP_CHECK_STORAGE)

            # 1) 서버 저장본
            cached = None if refresh else report_cache.load(cache_dir, number)
            if cached:
                try:
                    contents = [(kind, name, path.read_bytes()) for kind, name, path in cached]
                except OSError as exc:  # 읽는 도중 저장본이 교체/삭제됨 -> ECM 에서 새로 받는다
                    logger.warning("KOLAS report cache read failed for %s: %s", number, exc)
                else:
                    saved = []
                    counts = {"word": 0, "pdf": 0, "anon": 0}
                    for position, (kind, name, data) in enumerate(contents, start=1):
                        saved.append(add_entry(zf, number, kind, name, data))
                        counts[kind] += 1
                        progress_step(
                            index, number, "서버 저장본 전달 중",
                            task_progress.STEP_CHECK_STORAGE + (task_progress.STEP_FILES_END - task_progress.STEP_CHECK_STORAGE) * position / len(contents),
                        )
                        yield from sink.drain()
                    succeeded.append((number, saved, SOURCE_CACHE))
                    rows.append(ProjectRow(number, counts, source=SOURCE_CACHE))
                    progress_done(index, number, "서버 저장본 전달 완료")
                    continue

            # 2) ECM
            progress_step(index, number, "ECM 프로젝트 폴더·zip 탐색 중", task_progress.STEP_LOCATING)
            try:
                located = locate_project_reports(pool, project)
            except Exception as exc:
                logger.warning("KOLAS report: %s lookup failed: %s", number, exc)
                # 시험성적서가 업로드되지 않은 경우: 분당 ECM 의 익명 시험성적서(Word)로 대체한다.
                progress_step(index, number, "분당 ECM 익명본 조회 중", task_progress.STEP_ANON_LOOKUP)
                try:
                    anon_client, where, anon_metas = find_anonymous_report_files(pool, project)
                except Exception as anon_exc:
                    failed.append((number, f"{exc} / 익명본 대체도 실패: {anon_exc}"))
                    rows.append(ProjectRow(number, {"word": 0, "pdf": 0, "anon": 0}, anon_reason=str(anon_exc)))
                    progress_done(index, number, "시험성적서를 찾지 못함")
                    continue
                located = Located(
                    anon_client, ANON_CENTER, where,
                    files=[("anon", meta) for meta in anon_metas], anonymous=True,
                )

            client, center, folder_name = located.client, located.center, located.folder_name
            saved = []
            fetched = []  # 저장소에 저장할 (kind, 파일명, bytes)
            file_errors = []
            counts = {"word": 0, "pdf": 0, "anon": 0}
            kind_errors = {}  # kind -> 첫 실패 사유 (찾았으나 받지 못한 경우)
            total_files = len(located.zip_entries) + len(located.files)
            handled_files = 0

            def file_fraction():
                span = task_progress.STEP_FILES_END - task_progress.STEP_LOCATED
                return task_progress.STEP_LOCATED + span * handled_files / max(total_files, 1)

            progress_step(index, number, f"시험성적서 {total_files}개 받는 중", task_progress.STEP_LOCATED)
            for kind, file_name, data, _zip_name in located.zip_entries:
                reason = verify_downloaded_bytes(data, file_name, 0)
                handled_files += 1
                if reason:
                    file_errors.append(f"{file_name}: 무결성 검증 실패 ({reason})")
                    kind_errors.setdefault(kind, f"무결성 검증 실패: {file_name}")
                    continue
                saved.append(add_entry(zf, number, kind, file_name, data))
                fetched.append((kind, _safe_zip_part(file_name), data))
                counts[kind] += 1
                progress_step(index, number, f"시험성적서 받는 중 ({handled_files}/{total_files})", file_fraction())
                yield from sink.drain()
            for kind, meta in located.files:
                file_name = unicodedata.normalize("NFC", str(meta.get("fileName") or "download"))
                try:
                    expected_size = int(meta.get("fileSize") or 0)
                    data = client.download_bytes(meta)
                    reason = verify_downloaded_bytes(data, file_name, expected_size)
                    if reason:
                        data = client.download_bytes(meta)
                        reason = verify_downloaded_bytes(data, file_name, expected_size)
                        if reason:
                            raise RuntimeError(f"무결성 검증 실패 ({reason})")
                except Exception as exc:
                    logger.warning("KOLAS report: %s/%s download failed: %s", number, file_name, exc)
                    file_errors.append(f"{file_name}: {exc}")
                    kind_errors.setdefault(kind, f"{file_name}: {exc}")
                    handled_files += 1
                    continue
                handled_files += 1
                saved.append(add_entry(zf, number, kind, file_name, data))
                fetched.append((kind, _safe_zip_part(file_name), data))
                counts[kind] += 1
                progress_step(index, number, f"시험성적서 받는 중 ({handled_files}/{total_files})", file_fraction())
                yield from sink.drain()

            # 각 센터 ECM 에서 찾은 최종본을 모두 정상으로 받은 경우에만 저장소에 확정한다
            # (일부 실패면 다음 요청에서 다시 시도). 분당 익명본은 저장하지 않는다.
            if fetched and not file_errors and not located.anonymous:
                report_cache.save(cache_dir, number, fetched, center=center, folder_name=folder_name)
            source = SOURCE_ANON if located.anonymous else (SOURCE_ZIP if located.zip_entries else SOURCE_ECM)
            if saved:
                succeeded.append((number, saved, source))
            if file_errors:
                failed.append((number, "일부 파일 실패 - " + " | ".join(file_errors)))
            rows.append(ProjectRow(
                number, counts, source=source, kind_errors=kind_errors,
                anonymous=located.anonymous, anon_reason=kind_errors.get("anon", ""),
            ))
            progress_done(index, number, "완료" if saved else "받은 파일 없음")
            yield from sink.drain()

        for offset, number in enumerate(missing_numbers):
            failed.append((number, "KOLAS 프로젝트 목록에 없음"))
            rows.append(ProjectRow(number, {"word": 0, "pdf": 0, "anon": 0}, unknown=True))
            progress_done(len(projects) + offset, number, "KOLAS 목록에 없음")

        if reporter is not None:
            reporter.finish(rows)
        zf.writestr(SUMMARY_NAME, build_summary(succeeded, failed, rows).encode("utf-8-sig"))
        yield from sink.drain()
    yield from sink.drain()


@dataclass
class ProjectRow:
    """프로젝트 1건의 word/pdf(및 익명) 시험성적서 유무. 로그의 [프로젝트별 파일 유무] 한 덩어리."""

    number: str
    counts: dict                       # {"word": n, "pdf": n, "anon": n} - 결과 zip 에 실제로 담긴 개수
    source: str = ""                   # 담긴 파일의 출처(서버 저장본 / ECM / ECM zip 안 / 익명본)
    kind_errors: dict = field(default_factory=dict)  # 찾았으나 받지 못한 종류 -> 사유
    anonymous: bool = False            # 익명본 대체를 시도해 성공했는지
    anon_reason: str = ""              # 익명본 대체를 시도했으나 실패한 사유
    unknown: bool = False              # KOLAS 프로젝트 목록에 없어 확인 불가

    @property
    def has_word(self):
        return self.counts.get("word", 0) > 0

    @property
    def has_pdf(self):
        return self.counts.get("pdf", 0) > 0

    @property
    def tried_anonymous(self):
        return self.anonymous or bool(self.anon_reason)


SOURCE_SHORT = {
    SOURCE_CACHE: "서버 저장본",
    SOURCE_ECM: "ECM",
    SOURCE_ZIP: "ECM zip 안에서 추출",
}


def row_lines(row):
    """프로젝트 1건에서 **확인이 필요한 이력만** 줄로 만든다. word/pdf 를 정상으로 받은 이력은 쓰지 않는다.

    - 원본 시험성적서가 없으면:      `<번호> word|pdf 시험성적서 찾을 수 없음`
    - 있었으나 받지 못했으면:        `<번호> word|pdf 시험성적서 다운로드 실패 (사유)`
    - 분당 ECM 익명본을 받았으면:    `<번호> 익명 시험성적서(word) 다운로드 (...)`  (익명은 성공도 기록)
    - 익명본도 못 받았으면:          `<번호> 익명 시험성적서(word) 찾을 수 없음/다운로드 실패 (사유)`
    - KOLAS 목록에 없는 번호:        `<번호> word|pdf 시험성적서 확인 불가 (...)`
    """
    lines = []
    for kind in ("word", "pdf"):
        if row.unknown:
            lines.append(f"{row.number} {kind} 시험성적서 확인 불가 (KOLAS 프로젝트 목록에 없음)")
            continue
        count = row.counts.get(kind, 0)
        if kind in row.kind_errors:
            suffix = " - 같은 형식의 다른 파일은 받음" if count else ""
            lines.append(f"{row.number} {kind} 시험성적서 다운로드 실패 ({row.kind_errors[kind]}){suffix}")
        elif not count:
            lines.append(f"{row.number} {kind} 시험성적서 찾을 수 없음")
    if row.anonymous and row.counts.get("anon", 0):
        lines.append(f"{row.number} 익명 시험성적서(word) 다운로드 ({row.counts['anon']}개, 분당 ECM 익명본으로 대체, 서버에 저장 안 함)")
    elif row.anonymous:
        lines.append(f"{row.number} 익명 시험성적서(word) 다운로드 실패 ({row.anon_reason})")
    elif row.anon_reason:
        lines.append(f"{row.number} 익명 시험성적서(word) 찾을 수 없음 ({row.anon_reason})")
    return lines


def build_summary(succeeded, failed, rows=None, now=None):
    """_다운로드_결과.txt 내용. 템플릿은 main/docs/09_kolas_page.md 의 '결과 로그 템플릿' 참고.

    성공 이력(프로젝트별 '있음', [성공] 목록)은 쓰지 않는다. 건수 요약과 확인이 필요한 이력, 실패·누락 사유만 남긴다.
    """
    now = now or datetime.now()
    lines = ["KOLAS 시험성적서 다운로드 결과", f"생성 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}"]
    if rows is not None:
        known = [row for row in rows if not row.unknown]
        complete = sum(1 for row in known if row.has_word and row.has_pdf)
        partial = sum(1 for row in known if row.has_word != row.has_pdf)
        none = sum(1 for row in known if not row.has_word and not row.has_pdf)
        anonymous = sum(1 for row in known if row.anonymous)
        unknown = len(rows) - len(known)
        summary = (
            f"요청 프로젝트 {len(rows)}건 | word·pdf 모두 있음 {complete}건 | 일부만 있음 {partial}건 | "
            f"모두 없음 {none}건 | 익명본 대체 {anonymous}건"
        )
        if unknown:
            summary += f" | 확인 불가 {unknown}건"
        lines.append(summary)
    lines.append(f"성공 프로젝트: {len(succeeded)}건 / 실패·누락: {len(failed)}건")
    lines.append("")
    if rows is not None:
        # 정상으로 받은 word/pdf 이력은 쓰지 않는다. 문제가 있거나 익명본으로 대체한 프로젝트만 나온다.
        issue_lines = [line for row in rows for line in row_lines(row)]
        lines.append("[확인 필요 이력]")
        if issue_lines:
            lines.extend(issue_lines)
        else:
            lines.append("없음 (모든 프로젝트의 word·pdf 시험성적서를 정상으로 받았습니다)")
        lines.append("")
    if failed:
        lines.append("[실패·누락]")
        for number, reason in failed:
            lines.append(f"{number}: {reason}")
    return "\n".join(lines) + "\n"
