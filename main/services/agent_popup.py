"""
Windows 에이전트 팝업 자동화 (7~8단계).

pywinauto를 사용하여:
1. '폴더 찾아보기' 팝업에서 새 폴더를 만들고 선택한다.
2. '전송현황' 창이 사라질 때까지 대기한다.
3. '시스템 알림' (중복 파일) 창이 뜨면 '덮어쓰기' 버튼을 클릭한다.
"""

import logging
import os
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger("main.services.agent_popup")

try:
    import pywinauto
    from pywinauto import Desktop
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False
    logger.warning("pywinauto가 설치되지 않았습니다.")


# --- 창 제목 ---
FOLDER_POPUP_TITLE = "폴더 찾아보기"
TRANSFER_STATUS_TITLE = "전송현황"
SYSTEM_ALERT_TITLE = "시스템 알림"

# --- 대기 시간 (초) ---
FOLDER_POPUP_WAIT = 10
TRANSFER_WAIT = 300
TRANSFER_POLL_INTERVAL = 2
SYSTEM_ALERT_WAIT = 3


@dataclass
class PopupResult:
    success: bool
    download_dir: str = ""
    error_step: str = ""
    error_message: str = ""
    had_duplicate_alert: bool = False


def _download_base_dir() -> str:
    return getattr(settings, "AGENT_DOWNLOAD_BASE_DIR", r"C:\Users\jh910\Downloads")


def handle_folder_popup_and_download(
    project_number: str,
    job_id: str = "",
    max_retries: int = 2,
) -> PopupResult:
    """폴더 찾아보기 팝업 처리 -> 전송현황 대기 -> 시스템 알림 처리.

    폴더 찾아보기 팝업이 뜨면:
    1. '새 폴더 만들기(M)' 버튼 클릭
    2. 프로젝트번호 입력
    3. '확인' 버튼 클릭
    4. 전송현황 창 대기
    5. 시스템 알림 처리
    """
    if not HAS_PYWINAUTO:
        return PopupResult(
            success=False,
            error_step="pywinauto 확인",
            error_message="pywinauto가 설치되지 않았습니다.",
        )

    folder_name = project_number

    for attempt in range(max_retries + 1):
        if attempt > 0:
            folder_name = f"{project_number}_{attempt + 1}"
            logger.info("중복 발생. 폴더명 변경 후 재시도: %s", folder_name)

        result = _try_download_once(folder_name)
        if result.success:
            return result

        if result.had_duplicate_alert and attempt < max_retries:
            continue

        return result

    return PopupResult(
        success=False,
        error_step="재시도 초과",
        error_message=f"최대 재시도 횟수({max_retries})를 초과했습니다.",
    )


def _try_download_once(folder_name: str) -> PopupResult:
    """1회 다운로드 시도."""
    download_dir = os.path.join(_download_base_dir(), folder_name)

    # Step 1: 폴더 찾아보기 팝업 대기
    try:
        folder_dlg = _wait_for_window(FOLDER_POPUP_TITLE, timeout=FOLDER_POPUP_WAIT)
        if folder_dlg is None:
            return PopupResult(
                success=False,
                error_step="폴더 찾아보기 대기",
                error_message="폴더 찾아보기 팝업이 표시되지 않았습니다.",
            )
        _create_new_folder_and_confirm(folder_dlg, folder_name)
    except Exception as exc:
        logger.exception("폴더 선택 팝업 처리 실패")
        return PopupResult(
            success=False,
            error_step="폴더 선택",
            error_message=str(exc),
        )

    # Step 2: 전송현황 창 대기
    try:
        _wait_for_transfer_complete()
    except Exception as exc:
        logger.exception("전송현황 대기 실패")
        return PopupResult(
            success=False,
            download_dir=download_dir,
            error_step="전송현황 대기",
            error_message=str(exc),
        )

    # Step 3: 시스템 알림 감지
    had_duplicate = _handle_system_alert_if_exists()
    if had_duplicate:
        return PopupResult(
            success=False,
            download_dir=download_dir,
            had_duplicate_alert=True,
            error_step="중복 파일 알림",
            error_message="중복 파일 시스템 알림이 발생했습니다.",
        )

    return PopupResult(success=True, download_dir=download_dir)


def _wait_for_window(title: str, timeout: int = 10):
    """지정 제목의 창이 나타날 때까지 대기한다."""
    desktop = Desktop(backend="uia")
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            windows = desktop.windows(title=title)
            if windows:
                return windows[0]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def _create_new_folder_and_confirm(dlg, folder_name: str) -> None:
    """폴더 찾아보기 팝업에서 새 폴더를 만들고 확인한다.

    팝업이 뜨면 기본 경로(Downloads)에 있는 상태이므로:
    1. '새 폴더 만들기(M)' 버튼 클릭
    2. 폴더명(프로젝트번호) 입력
    3. '확인' 버튼 클릭
    """
    app = pywinauto.Application(backend="uia").connect(handle=dlg.handle)
    dialog = app.window(title=FOLDER_POPUP_TITLE)
    dialog.wait("visible", timeout=5)

    # '새 폴더 만들기(M)' 버튼 찾기
    new_folder_btn = None
    for btn_title in ["새 폴더 만들기(&M)", "새 폴더 만들기(M)", "새 폴더 만들기"]:
        try:
            btn = dialog.child_window(title=btn_title, control_type="Button")
            if btn.exists(timeout=2):
                new_folder_btn = btn
                break
        except Exception:
            continue

    if new_folder_btn is None:
        # fallback: 버튼 텍스트에 "폴더" 포함된 것 찾기
        try:
            new_folder_btn = dialog.child_window(title_re=".*폴더.*만들기.*", control_type="Button")
        except Exception:
            raise RuntimeError("'새 폴더 만들기' 버튼을 찾을 수 없습니다.")

    new_folder_btn.click()
    time.sleep(0.5)

    # 새 폴더명 입력 (인라인 편집 상태가 됨)
    # SHBrowseForFolder에서 새 폴더 만들기 시 트리뷰 내에 편집창이 생김
    tree = dialog.child_window(class_name="SysTreeView32")
    if not tree.exists(timeout=2):
        tree = dialog.child_window(control_type="Tree")

    # 편집 컨트롤 찾기 (새 폴더 만들기 후 인라인 에디트가 활성화됨)
    edit = None
    for _ in range(10):
        try:
            edit = tree.child_window(control_type="Edit")
            if edit.exists(timeout=0.5):
                break
        except Exception:
            pass
        time.sleep(0.3)

    if edit is None or not edit.exists(timeout=1):
        # fallback: dialog 전체에서 Edit 찾기
        edit = dialog.child_window(control_type="Edit")

    if not edit.exists(timeout=2):
        raise RuntimeError("새 폴더 이름 입력 필드를 찾을 수 없습니다.")

    edit.set_text(folder_name)
    time.sleep(0.3)

    # Enter 키로 폴더명 확정
    edit.type_keys("{ENTER}", with_spaces=True)
    time.sleep(0.5)

    # '확인' 버튼 클릭
    ok_btn = dialog.child_window(title="확인", control_type="Button")
    if not ok_btn.exists(timeout=2):
        ok_btn = dialog.child_window(title="OK", control_type="Button")
    ok_btn.click()
    logger.info("새 폴더 생성 및 선택 완료: %s", folder_name)


def _wait_for_transfer_complete() -> None:
    """전송현황 창이 뜨고 사라질 때까지 대기한다.

    전송현황 창이 사라지면 다운로드(파일 생성)가 완료된 것이다.
    """
    logger.info("전송현황 창 대기 중...")
    transfer_dlg = _wait_for_window(TRANSFER_STATUS_TITLE, timeout=10)
    if transfer_dlg is None:
        logger.info("전송현황 창이 표시되지 않았습니다. 이미 완료되었을 수 있습니다.")
        return

    logger.info("전송현황 창 감지됨. 다운로드 완료 대기 중...")
    end_time = time.time() + TRANSFER_WAIT
    while time.time() < end_time:
        desktop = Desktop(backend="uia")
        windows = desktop.windows(title=TRANSFER_STATUS_TITLE)
        if not windows:
            logger.info("전송현황 창이 사라졌습니다. 다운로드 완료.")
            return
        time.sleep(TRANSFER_POLL_INTERVAL)

    raise RuntimeError(f"전송현황 창이 {TRANSFER_WAIT}초 내에 사라지지 않았습니다.")


def _handle_system_alert_if_exists() -> bool:
    """시스템 알림 (중복 파일) 창이 있으면 '덮어쓰기' 버튼을 클릭한다.

    Returns:
        True: 시스템 알림이 있었고 처리했다.
        False: 시스템 알림이 없었다.
    """
    time.sleep(SYSTEM_ALERT_WAIT)

    alert_dlg = _wait_for_window(SYSTEM_ALERT_TITLE, timeout=3)
    if alert_dlg is None:
        return False

    logger.warning("시스템 알림 (중복 파일) 감지됨.")
    try:
        app = pywinauto.Application(backend="uia").connect(handle=alert_dlg.handle)
        dialog = app.window(title=SYSTEM_ALERT_TITLE)

        overwrite_btn = dialog.child_window(title="덮어쓰기", control_type="Button")
        if overwrite_btn.exists(timeout=3):
            overwrite_btn.click()
            logger.info("덮어쓰기 버튼 클릭 완료.")
        else:
            cancel_btn = dialog.child_window(title="취소", control_type="Button")
            if cancel_btn.exists(timeout=2):
                cancel_btn.click()
    except Exception as exc:
        logger.exception("시스템 알림 처리 실패: %s", exc)

    return True
