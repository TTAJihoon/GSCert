"""로컬 앱(exe) 자체 자동 업데이트.

Windows는 실행 중인 프로세스 자신의 exe/DLL을 덮어쓰지 못하게 막는다(onedir로
패키징된 이 앱은 Qt DLL 등 `_internal/` 전체가 실행 중 내내 잠긴다). 그래서 다른
자동 업데이트 프로그램들과 같은 방식을 쓴다: 앱이 새 버전을 임시 폴더에 받아두고,
자신이 만든 배치 스크립트를 분리된 프로세스로 띄운 뒤 스스로 종료한다. 배치는
현재 프로세스가 완전히 끝나길 기다렸다가(파일 잠금이 풀림) robocopy로 설치 폴더를
새 버전으로 교체하고 앱을 다시 실행한다.

호출 순서: `download_and_stage_update()` → (성공하면) 앱을 닫기 직전에
`launch_update_and_exit()`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from .cert_trust import resource_path


def bundled_app_version() -> str:
    """이 exe(또는 개발 모드 소스)에 번들된 APP_VERSION 값. 못 찾으면 빈 문자열."""
    path = resource_path("APP_VERSION")
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """현재 실행 중인 exe가 설치된 폴더(dist/GSCertLocalReviewDashboard 에 해당)."""
    return Path(sys.executable).resolve().parent


class UpdateError(RuntimeError):
    pass


def download_and_stage_update(client, *, exe_name: str = "GSCertLocalReviewDashboard.exe") -> Path:
    """새 버전을 내려받아 압축을 풀고, 실행 파일이 있는 폴더 경로를 반환한다.

    아직 아무것도 교체하지 않는다 — 실제 교체+재실행은 `launch_update_and_exit()`가
    한다. 이렇게 나눠 둬야 다운로드/압축 해제가 실패해도 현재 설치는 그대로 안전하다.
    """
    if not is_frozen():
        raise UpdateError("개발 모드(소스 실행)에서는 자동 업데이트를 지원하지 않습니다.")

    staging_dir = Path(tempfile.mkdtemp(prefix="gscert_update_"))
    zip_path = staging_dir / "update.zip"
    extract_dir = staging_dir / "extracted"

    client.download_app_package(zip_path)
    if not zip_path.is_file() or zip_path.stat().st_size < 1024:
        raise UpdateError("다운로드한 업데이트 파일이 비정상적으로 작습니다.")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise UpdateError("다운로드한 업데이트 파일이 손상되었습니다.") from exc

    new_root = _find_folder_containing(extract_dir, exe_name)
    if new_root is None:
        raise UpdateError("다운로드한 업데이트에서 실행 파일을 찾을 수 없습니다.")
    return new_root


def launch_update_and_exit(new_root: Path, *, exe_name: str = "GSCertLocalReviewDashboard.exe") -> None:
    """교체용 배치를 분리된 프로세스로 띄우고 현재 프로세스를 즉시 종료한다.

    이 함수는 반환하지 않는다(os._exit로 끝낸다) — 호출부가 정리 코드를 더 실행하지
    못하므로, 저장할 설정 등은 이 함수를 부르기 *전에* 먼저 처리해야 한다.
    """
    current_dir = install_dir()
    current_exe = current_dir / exe_name
    bat_path = new_root.parent / "apply_update.bat"
    _write_update_batch(
        bat_path,
        pid=os.getpid(),
        source_dir=new_root,
        target_dir=current_dir,
        exe_path=current_exe,
    )

    # DETACHED_PROCESS(콘솔 자체가 없음)로 띄우면 배치 안의 tasklist/find 파이프와
    # `start`의 재실행이 실측에서 멈추거나 실패했다 — cmd 계열 명령은 콘솔이 아예
    # 없는 것보다 "숨겨진" 콘솔(CREATE_NO_WINDOW)에서 훨씬 안정적으로 동작한다.
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
        cwd=str(new_root.parent),
    )
    os._exit(0)


def _find_folder_containing(root: Path, file_name: str) -> Path | None:
    if (root / file_name).is_file():
        return root
    for child in root.iterdir():
        if child.is_dir():
            found = _find_folder_containing(child, file_name)
            if found is not None:
                return found
    return None


def _write_update_batch(bat_path: Path, *, pid: int, source_dir: Path, target_dir: Path, exe_path: Path) -> None:
    # tasklist로 이전 프로세스(pid)가 완전히 종료될 때까지 기다린 뒤에만 교체한다
    # (그 전에 robocopy를 돌리면 아직 파일이 잠겨 있어 실패한다).
    #
    # 대기에는 `timeout`이 아니라 `ping`을 쓴다 — 이 배치는 콘솔이 없는
    # DETACHED_PROCESS로 실행되는데, `timeout`은 콘솔/표준입력이 없으면
    # "Input redirection is not supported"로 즉시 실패하거나(환경에 따라)
    # 아예 멈춰버려서 교체가 영원히 진행되지 않는 걸 실측으로 확인했다.
    # `ping`은 표준입력을 쓰지 않아 콘솔 유무와 무관하게 항상 동작한다.
    # 명령들도 PATH 대신 %SystemRoot%\\System32 절대경로로 불러 PATH에 다른
    # 동명 프로그램(예: Git bash의 coreutils timeout)이 끼어들 여지를 없앤다.
    script = f"""@echo off
setlocal
set "PID={pid}"
set "SRC={source_dir}"
set "DST={target_dir}"
set "EXE={exe_path}"
set "SYS=%SystemRoot%\\System32"

:waitloop
"%SYS%\\tasklist.exe" /FI "PID eq %PID%" 2>NUL | "%SYS%\\find.exe" /I "%PID%" >NUL
if not errorlevel 1 (
    "%SYS%\\PING.EXE" -n 2 127.0.0.1 >NUL
    goto waitloop
)

"%SYS%\\robocopy.exe" "%SRC%" "%DST%" /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS >NUL
start "" "%EXE%"
"""
    bat_path.write_text(script, encoding="utf-8")
