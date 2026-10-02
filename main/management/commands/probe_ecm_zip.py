r"""ECM 의 zip 을 통째로 받지 않고 내부 '시험성적서'를 찾을 수 있는지 실서버에서 확인하는 명령(결정 12b 개정 2026-10-01: 접속 가능한 환경이면 Claude 가 직접 실행해도 됨, 읽기 전용·용량 상한).

확인 순서:
  1. 프로젝트 폴더를 찾고 파일 목록만 조회해 .zip 파일과 크기를 보여준다(다운로드 없음).
  2. 선택한 zip 에 HTTP Range 요청(처음 4바이트)을 보내 부분 읽기가 되는지 확인한다.
     Range 를 무시하고 전체(200)로 응답하면 본문을 읽지 않고 즉시 연결을 닫는다.
  3. 되면 zip 끝의 목록(central directory)만 받아 내부 파일 이름을 나열하고 '시험성적서' Word/PDF 를 찾는다.
  4. --extract 를 주면 찾은 파일만 받아 저장한다.
어느 단계에서도 --max-mb(기본 30MB)를 넘겨 받지 않는다.

사용 예(PowerShell, env.ps1 로드 후):
    # zip 목록만 보기(다운로드 없음)
    .\.venv\Scripts\python.exe -X utf8 manage.py probe_ecm_zip --center sangam --test-no GS-A-25-0077 --list-only

    # Range 지원 여부 + zip 내부 시험성적서 찾기(목록만 받음)
    .\.venv\Scripts\python.exe -X utf8 manage.py probe_ecm_zip --center sangam --test-no GS-A-25-0077

    # 찾은 시험성적서까지 실제로 받아 저장
    .\.venv\Scripts\python.exe -X utf8 manage.py probe_ecm_zip --center sangam --test-no GS-A-25-0077 --extract
"""

from __future__ import annotations

import tempfile
import time
import unicodedata
import zipfile
from pathlib import PurePosixPath, Path

from django.core.management.base import BaseCommand, CommandError


def _mb(value):
    return f"{value / 1024 / 1024:,.1f}MB"


class Command(BaseCommand):
    help = "ECM zip 파일을 통째로 받지 않고 내부 시험성적서를 찾을 수 있는지(HTTP Range) 실서버에서 검증한다."

    def add_arguments(self, parser):
        parser.add_argument("--center", default="sangam", help="센터 코드(sangam/bundang/yeongnam)")
        parser.add_argument("--test-no", required=True, help="시험번호(예: GS-A-25-0077, TTA-26-00009)")
        parser.add_argument("--date", default="", help="인증일(연도 추정용, 예: 2025-12-29), 선택")
        parser.add_argument("--zip-name", default="", help="이름에 이 문자열이 든 zip 만 대상으로 한다(기본: 가장 큰 zip)")
        parser.add_argument("--list-only", action="store_true", help="zip 파일 목록과 크기만 보고 끝낸다(다운로드 없음)")
        parser.add_argument("--extract", action="store_true", help="찾은 시험성적서를 실제로 받아 저장한다")
        parser.add_argument("--dest", default="", help="--extract 저장 폴더(미지정 시 임시 폴더)")
        parser.add_argument("--max-mb", type=float, default=30.0, help="이 실행에서 받을 최대 용량(MB)")
        parser.add_argument("--block-kb", type=int, default=256, help="Range 요청 블록 크기(KB)")

    def handle(self, *args, **options):
        from main.views.review.artifact_source import verify_downloaded_bytes
        from main.views.review.ecm_http_client import EcmRangeUnsupported, build_client
        from main.views.review.ecm_download_review_centers import normalize_center_code
        from main.views.review.ecm_zip_range import (
            RangeBudgetExceeded,
            iter_entries,
            open_remote_zip,
        )
        from main.views.review.kolas_report_download import classify_report_file

        center = normalize_center_code(options["center"])
        test_no = unicodedata.normalize("NFC", options["test_no"]).strip()
        max_bytes = int(options["max_mb"] * 1024 * 1024)
        out = self.stdout.write

        # 1) 폴더 탐색 + 파일 목록(다운로드 없음)
        try:
            client = build_client(center)
            client.login()
        except Exception as exc:
            raise CommandError(f"ECM 로그인 실패(center={center}): {exc}") from exc
        folder = client.find_full_project_folder(test_no, options["date"], center)
        if not folder:
            raise CommandError(f"프로젝트 폴더를 찾지 못했습니다: {test_no} (center={center})")
        out(f"프로젝트 폴더: {folder['name']}")

        zips = []
        total_files = 0
        for rel, meta in client.walk_files(folder["oid"]):
            total_files += 1
            if str(meta.get("fileName", "")).lower().endswith(".zip"):
                zips.append(("/".join(rel), meta))
        out(f"파일 {total_files}개, zip {len(zips)}개")
        for rel, meta in zips:
            out(f"  - {rel + '/' if rel else ''}{meta['fileName']}  ({_mb(int(float(meta.get('fileSize') or 0)))})")
        if not zips:
            raise CommandError("이 프로젝트에는 zip 파일이 없습니다. 다른 프로젝트로 시도하세요.")
        if options["list_only"]:
            return

        keyword = options["zip_name"]
        candidates = [item for item in zips if keyword in item[1]["fileName"]] if keyword else zips
        if not candidates:
            raise CommandError(f"--zip-name '{keyword}' 에 맞는 zip 이 없습니다.")
        rel, meta = max(candidates, key=lambda item: int(float(item[1].get("fileSize") or 0)))
        size = int(float(meta.get("fileSize") or 0))
        out(f"\n대상 zip: {meta['fileName']}  ({_mb(size)})")

        # 2) Range 지원 확인 (처음 4바이트)
        started = time.time()
        try:
            head = client.blob_range(meta, 0, 3)
        except EcmRangeUnsupported as exc:
            out(self.style.ERROR(f"[Range 미지원] {exc}"))
            out("→ 서버가 부분 읽기를 지원하지 않습니다. 아래 대안을 검토하세요(분석 문서 참고):")
            out("   · 브라우저 개발자도구로 ECM 화면의 zip '미리보기/압축파일 보기' 요청을 캡처해 내부 목록 API 가 있는지 확인")
            out("   · 스트리밍 순차 해제(앞쪽에 있으면 조기 중단) / ECM 업로드 시 압축 해제 업로드")
            return
        except Exception as exc:
            raise CommandError(f"Range 요청 실패: {exc}") from exc
        out(f"[Range 지원] 처음 4바이트 = {head!r} (zip 이면 b'PK\\x03\\x04')  ({time.time() - started:.1f}s)")
        if not head.startswith(b"PK"):
            out(self.style.WARNING("zip 시그니처가 아닙니다 - DRM/암호화 또는 다른 형식일 수 있습니다."))
            return

        # 3) 끝부분 목록만 받아 내부 파일 나열
        started = time.time()
        try:
            zf, remote = open_remote_zip(
                client, meta, block_size=options["block_kb"] * 1024, max_bytes=max_bytes,
            )
        except RangeBudgetExceeded as exc:
            raise CommandError(f"{exc} --max-mb 를 늘리거나 zip 이 비정상적으로 큰 목록을 가졌는지 확인하세요.") from exc
        except zipfile.BadZipFile as exc:
            raise CommandError(f"zip 목록을 읽지 못했습니다: {exc} (분할 압축/암호화/손상 가능)") from exc
        entries = list(iter_entries(zf))
        out(
            f"zip 목록 읽기 완료: 항목 {len(entries)}개, 요청 {remote.requests}회, "
            f"전송 {_mb(remote.bytes_fetched)} / 전체 {_mb(size)} ({remote.bytes_fetched / size:.2%}), "
            f"{time.time() - started:.1f}s"
        )

        matches = []
        nested = []
        encrypted = 0
        for name, info in entries:
            base = PurePosixPath(name.replace("\\", "/")).name
            kind = classify_report_file(base)
            if kind:
                matches.append((kind, name, info))
            if base.lower().endswith(".zip"):
                nested.append((name, info))
            if info.flag_bits & 0x1:
                encrypted += 1

        out(f"\n시험성적서 Word/PDF: {len(matches)}개")
        for kind, name, info in matches:
            method = "stored" if info.compress_type == zipfile.ZIP_STORED else f"compressed({info.compress_type})"
            out(f"  - [{kind}] {name}  (압축 {_mb(info.compress_size)} / 원본 {_mb(info.file_size)}, {method})")
        if nested:
            out(f"\n중첩 zip {len(nested)}개 (안에 또 zip 이 있음):")
            for name, info in nested[:20]:
                method = "stored(부분읽기 가능)" if info.compress_type == zipfile.ZIP_STORED else "compressed(통째로 풀어야 함)"
                out(f"  - {name}  ({_mb(info.compress_size)}, {method})")
        if encrypted:
            out(self.style.WARNING(f"\n암호화된 항목 {encrypted}개 - 암호 없이는 읽을 수 없습니다."))
        names_sample = [name for name, _ in entries[:5]]
        out(f"\n이름 복원 확인용 앞 5개: {names_sample}")
        if not matches:
            out(self.style.WARNING("이 zip 안에서 '시험성적서' Word/PDF 를 찾지 못했습니다. 위 이름 목록으로 실제 파일명을 확인하세요."))

        # 4) 선택: 찾은 파일만 받아 저장
        if options["extract"] and matches:
            dest = Path(options["dest"]) if options["dest"] else Path(tempfile.mkdtemp(prefix="probe_ecm_zip_"))
            dest.mkdir(parents=True, exist_ok=True)
            out(f"\n추출 저장 폴더: {dest}")
            for kind, name, info in matches:
                started = time.time()
                try:
                    data = zf.open(info).read()
                except RangeBudgetExceeded as exc:
                    out(self.style.ERROR(f"  - {name}: {exc}"))
                    continue
                base = PurePosixPath(name.replace("\\", "/")).name
                reason = verify_downloaded_bytes(data, base, 0)
                target = dest / kind / base
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                status = "OK" if not reason else f"무결성 경고: {reason}"
                out(f"  - [{kind}] {base}  {_mb(len(data))}  {status}  ({time.time() - started:.1f}s)")
            out(
                f"\n최종 전송량: {_mb(remote.bytes_fetched)} / zip 전체 {_mb(size)} "
                f"({remote.bytes_fetched / size:.2%}), 요청 {remote.requests}회"
            )
        elif matches:
            out("\n(--extract 를 주면 찾은 파일을 실제로 받아 저장하고 최종 전송량을 보여줍니다.)")
