r"""ECM HTTP 직접연동 실서버 검증 명령(결정 12b — 사용자 PC 에서 실행).

Claude 의 명령 샌드박스는 외부 네트워크(210.x)로 나갈 수 없으므로, 실제 로그인/폴더탐색/
다운로드가 되는지는 사용자가 자신의 PC(실서버)에서 이 명령으로 확인한다. 운영 코드와 동일한
경로(`build_client` → `DestinyECM`)를 타므로, 여기서 통과하면 워커의 `ecm-http` source 도
같은 방식으로 동작한다.

사용 예(PowerShell, env.ps1 로드 후):
    # 프로젝트 폴더 탐색 + 파일 개수만(다운로드 없음)
    .\.venv\Scripts\python.exe manage.py verify_ecm_http --center sangam --test-no GS-C-24-0003 --date 2024-01-01

    # 실제 다운로드까지(임시 폴더)
    .\.venv\Scripts\python.exe manage.py verify_ecm_http --center bundang --test-no GS-A-23-0336 --download

설정: 자격증명은 환경변수(ECM_USERNAME/ECM_PASSWORD[_BUNDANG]) 로만 주입한다.
"""

from __future__ import annotations

import tempfile
import unicodedata
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "ECM HTTP 직접연동으로 로그인→프로젝트 폴더 탐색→(선택)다운로드를 실서버에서 검증한다."

    def add_arguments(self, parser):
        parser.add_argument("--center", default="sangam", help="센터 코드(sangam/bundang/yeongnam)")
        parser.add_argument("--test-no", required=True, help="시험번호(예: GS-A-23-0336, TTA-26-00009)")
        parser.add_argument("--date", default="", help="인증일(연도 추정용, 예: 2024-01-01)")
        parser.add_argument("--grade", default="", help="등급 필터(1/2), 선택")
        parser.add_argument("--download", action="store_true", help="파일을 실제로 내려받아 무결성까지 검증")
        parser.add_argument("--dest", default="", help="다운로드 대상 폴더(미지정 시 임시 폴더)")
        parser.add_argument("--limit", type=int, default=0, help="다운로드할 최대 파일 수(0=무제한)")

    def handle(self, *args, **options):
        from main.views.review.artifact_source import verify_downloaded_bytes
        from main.views.review.ecm_download_review_centers import (
            ecm_base_url,
            ecm_root_oid,
            normalize_center_code,
        )
        from main.views.review.ecm_http_client import EcmClientError, build_client

        center = normalize_center_code(options["center"])
        test_no = options["test_no"]

        self.stdout.write(f"센터={center}  base_url={ecm_base_url(center)}  root_oid={ecm_root_oid(center)}")

        try:
            client = build_client(center)
        except EcmClientError as exc:
            raise CommandError(str(exc))

        # 1) 로그인
        try:
            client.login()
        except Exception as exc:
            raise CommandError(f"로그인 실패: {exc}")
        self.stdout.write(self.style.SUCCESS("로그인 OK (SESSION_KEY 확보)"))

        # 2) 프로젝트 폴더 탐색
        found = client.find_project_folder(test_no, options["date"], options["grade"])
        if not found:
            raise CommandError(f"프로젝트 폴더를 찾지 못했습니다: {test_no}")
        self.stdout.write(
            self.style.SUCCESS(f"프로젝트 폴더: {found['name']}  (oid={found['oid']}, root={found.get('root','')})")
        )

        # 3) 재귀 순회 — 폴더별 파일 개수
        total_files = 0
        total_folders = 0
        drm_files = 0
        leaf_targets = []  # (relative_path, files)

        def walk(oid, rel):
            nonlocal total_files, total_folders, drm_files
            contents = client.folder_contents(oid)
            files = contents.get("files") or []
            if files:
                total_folders += 1
                total_files += len(files)
                drm_files += sum(1 for f in files if f.get("drm"))
                leaf_targets.append((rel, files))
                self.stdout.write(f"  [{'/'.join(rel) or '.'}]  파일 {len(files)}개")
            for child in contents.get("folders") or []:
                if child.get("oid"):
                    walk(child["oid"], rel + [child.get("name", "")])

        walk(found["oid"], [])
        self.stdout.write(
            self.style.SUCCESS(f"탐색 완료: 파일 있는 폴더 {total_folders}개, 파일 {total_files}개, DRM 표시 {drm_files}개")
        )

        if not options["download"]:
            self.stdout.write("(--download 미지정 → 다운로드 생략. 탐색까지만 검증)")
            return

        # 4) 다운로드 + 무결성 검증
        dest_root = Path(options["dest"]) if options["dest"] else Path(tempfile.mkdtemp(prefix="ecm_http_verify_"))
        project_number = unicodedata.normalize("NFC", test_no)
        limit = options["limit"]
        done = 0
        failures = []
        for rel, files in leaf_targets:
            segments = [project_number] + [unicodedata.normalize("NFC", p) for p in rel]
            target_dir = dest_root.joinpath(*segments)
            target_dir.mkdir(parents=True, exist_ok=True)
            for meta in files:
                if limit and done >= limit:
                    break
                name = unicodedata.normalize("NFC", meta.get("fileName") or "")
                data = client.download_bytes(meta)
                reason = verify_downloaded_bytes(data, name, int(meta.get("fileSize") or 0))
                if reason:
                    failures.append(f"{'/'.join(rel)}/{name}: {reason}")
                    self.stdout.write(self.style.ERROR(f"  FAIL {name}: {reason}"))
                else:
                    (target_dir / name).write_bytes(data)
                    self.stdout.write(f"  OK   {name} ({len(data)} bytes)")
                done += 1
            if limit and done >= limit:
                break

        self.stdout.write(f"다운로드 위치: {dest_root}")
        if failures:
            raise CommandError(f"무결성 검증 실패 {len(failures)}건:\n  " + "\n  ".join(failures))
        self.stdout.write(self.style.SUCCESS(f"다운로드 + 무결성 검증 OK ({done}개)"))
