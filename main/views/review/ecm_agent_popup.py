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

logger = logging.getLogger("main.views.review.ecm_agent_popup")

try:
    import pywinauto
    from pywinauto import Desktop
    from pywinauto.application import process_module
    from pywinauto.keyboard import send_keys
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False
    logger.warning("pywinauto가 설치되지 않았습니다.")


# --- 창 제목 ---
FOLDER_POPUP_TITLE = "폴더 찾아보기"
FOLDER_POPUP_TITLES = ("폴더 찾아보기", "폴더 선택", "Browse For Folder")
FOLDER_POPUP_CLASSES = ("#32770", "CabinetWClass")
FOLDER_POPUP_PROCESS_HINTS = ("DestinyECMAgent", "chrome", "msedge")
TRANSFER_STATUS_TITLE = "전송현황"
SYSTEM_ALERT_TITLE = "시스템 알림"

# --- 대기 시간 (초) ---
FOLDER_POPUP_WAIT = 30
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


def _folder_popup_wait() -> int:
    return int(getattr(settings, "AGENT_FOLDER_POPUP_WAIT", FOLDER_POPUP_WAIT))


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
    folder_name = _available_folder_name(folder_name)
    download_dir = os.path.join(_download_base_dir(), folder_name)

    # Step 1: 폴더 찾아보기 팝업 대기
    try:
        folder_dlg = _wait_for_any_window(FOLDER_POPUP_TITLES, timeout=_folder_popup_wait())
        if folder_dlg is None:
            windows = _describe_open_windows()
            return PopupResult(
                success=False,
                error_step="폴더 찾아보기 대기",
                error_message=f"폴더 찾아보기 팝업이 표시되지 않았습니다. open_windows={windows}",
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


def _available_folder_name(base_name: str) -> str:
    """Downloads 아래에 아직 없는 폴더명을 고른다."""
    candidate = base_name
    index = 2
    while os.path.exists(os.path.join(_download_base_dir(), candidate)):
        candidate = f"{base_name}_{index}"
        index += 1
    return candidate


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


def _wait_for_any_window(titles, timeout: int = 10):
    end_time = time.time() + timeout
    last_candidate_log = 0.0
    while time.time() < end_time:
        title_window = _find_window_by_title(titles)
        if title_window is not None:
            logger.info("폴더 선택 팝업 감지(title): %s", _window_description(title_window))
            return title_window

        candidate = _find_folder_popup_candidate(titles)
        if candidate is not None:
            logger.info("폴더 선택 팝업 감지(candidate): %s", _window_description(candidate))
            return candidate

        now = time.time()
        if now - last_candidate_log >= 5:
            logger.info("폴더 선택 팝업 대기 중. candidates=%s", _describe_popup_candidates())
            last_candidate_log = now
        time.sleep(0.5)
    return None


def _find_window_by_title(titles):
    try:
        desktop = Desktop(backend="uia")
        for title in titles:
            try:
                windows = desktop.windows(title=title)
                if windows:
                    return windows[0]
            except Exception:
                pass
    except Exception:
        logger.debug("UIA title window search failed", exc_info=True)
    return None


def _find_folder_popup_candidate(titles):
    try:
        desktop = Desktop(backend="win32")
        windows = desktop.windows()
    except Exception:
        logger.debug("Win32 folder popup search failed", exc_info=True)
        return None

    for window in windows:
        try:
            if _is_folder_popup_candidate(window, titles):
                return window
        except Exception:
            logger.debug("folder popup candidate check failed", exc_info=True)
    return None


def _is_folder_popup_candidate(window, titles) -> bool:
    title = _safe_window_text(window)
    class_name = _safe_class_name(window)
    if title in titles or any(title_part in title for title_part in titles):
        return True
    if title in (TRANSFER_STATUS_TITLE, SYSTEM_ALERT_TITLE):
        return False
    if class_name not in FOLDER_POPUP_CLASSES:
        return False
    try:
        if not window.is_visible():
            return False
    except Exception:
        return False

    module = _safe_process_module(window)
    module_lower = module.lower()
    has_process_hint = any(hint.lower() in module_lower for hint in FOLDER_POPUP_PROCESS_HINTS)
    children = _child_text_snapshot(window)
    child_blob = " ".join(children)
    has_folder_controls = (
        "새 폴더" in child_blob
        or "폴더 만들기" in child_blob
        or ("확인" in child_blob and ("취소" in child_blob or "Cancel" in child_blob))
    )
    return has_process_hint and has_folder_controls


def _describe_open_windows(limit: int = 20) -> str:
    try:
        desktop = Desktop(backend="win32")
        descriptions = []
        for window in desktop.windows():
            try:
                if not _is_interesting_window(window):
                    continue
                descriptions.append(_window_description(window))
            except Exception:
                continue
            if len(descriptions) >= limit:
                break
        return " | ".join(descriptions) if descriptions else "<none>"
    except Exception as exc:
        return f"<window list failed: {exc}>"


def _describe_popup_candidates(limit: int = 12) -> str:
    try:
        desktop = Desktop(backend="win32")
        descriptions = []
        for window in desktop.windows():
            try:
                if not _is_popup_candidate_for_log(window):
                    continue
                descriptions.append(_window_description(window, include_children=True))
            except Exception:
                continue
            if len(descriptions) >= limit:
                break
        return " || ".join(descriptions) if descriptions else "<none>"
    except Exception as exc:
        return f"<candidate list failed: {exc}>"


def _is_interesting_window(window) -> bool:
    title = _safe_window_text(window)
    class_name = _safe_class_name(window)
    module = _safe_process_module(window).lower()
    if title:
        return True
    if class_name in FOLDER_POPUP_CLASSES:
        return True
    return any(hint.lower() in module for hint in FOLDER_POPUP_PROCESS_HINTS)


def _is_popup_candidate_for_log(window) -> bool:
    title = _safe_window_text(window)
    class_name = _safe_class_name(window)
    module = _safe_process_module(window).lower()
    if any(token in title for token in ("폴더", "다운로드", "전송", "Agent", "Destiny")):
        return True
    if class_name in FOLDER_POPUP_CLASSES:
        return True
    return any(hint.lower() in module for hint in FOLDER_POPUP_PROCESS_HINTS)


def _window_description(window, include_children: bool = False) -> str:
    parts = [
        f"handle={getattr(window, 'handle', '')}",
        f"pid={_safe_process_id(window)}",
        f"class={_safe_class_name(window)}",
        f"visible={_safe_visible(window)}",
        f"title={_safe_window_text(window)!r}",
    ]
    module = _safe_process_module(window)
    if module:
        parts.append(f"module={module}")
    if include_children:
        children = _child_text_snapshot(window, limit=8)
        if children:
            parts.append(f"children={children}")
    return " ".join(parts)


def _safe_window_text(window) -> str:
    try:
        return window.window_text() or ""
    except Exception:
        return ""


def _safe_class_name(window) -> str:
    try:
        return window.class_name() or ""
    except Exception:
        return ""


def _safe_process_id(window):
    try:
        return window.process_id()
    except Exception:
        return ""


def _safe_visible(window):
    try:
        return window.is_visible()
    except Exception:
        return ""


def _safe_process_module(window) -> str:
    try:
        pid = window.process_id()
        return process_module(pid) or ""
    except Exception:
        return ""


def _child_text_snapshot(window, limit: int = 20) -> list[str]:
    texts = []
    try:
        children = window.children()
    except Exception:
        return texts
    for child in children:
        try:
            text = child.window_text()
        except Exception:
            text = ""
        if text:
            texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def _connect_dialog(dlg):
    app = pywinauto.Application(backend="uia").connect(handle=dlg.handle)
    dialog = app.window(handle=dlg.handle)
    dialog.wait("visible", timeout=5)
    try:
        dialog.set_focus()
    except Exception:
        pass
    return dialog


def _select_existing_folder_and_confirm(dlg, folder_name: str) -> None:
    """폴더 찾아보기 팝업에서 미리 만든 프로젝트 폴더를 선택하고 확인한다.

    팝업이 뜨기 전에 `Downloads/{프로젝트번호}` 폴더를 만들어두고,
    기본 다운로드 경로 아래에서 해당 폴더를 찾아 선택한다.
    """
    dialog = _connect_dialog(dlg)

    try:
        _select_existing_folder_uia(dialog, folder_name)
        return
    except Exception:
        logger.warning("UIA 폴더 선택 실패. 키보드 fallback을 시도합니다.", exc_info=True)
        _select_existing_folder_keyboard(dialog, folder_name)


def _select_existing_folder_uia(dialog, folder_name: str) -> None:
    """UIA control tree를 사용해 기존 프로젝트 폴더를 선택한다."""
    target = None
    try:
        target = dialog.child_window(title=folder_name, control_type="TreeItem")
        if not target.exists(timeout=3):
            target = None
    except Exception:
        target = None

    if target is None:
        for item in dialog.descendants(control_type="TreeItem"):
            try:
                if item.window_text() == folder_name:
                    target = item
                    break
            except Exception:
                continue

    if target is None:
        raise RuntimeError(f"프로젝트 폴더 TreeItem을 찾을 수 없습니다: {folder_name}")

    _select_tree_item(target, folder_name)
    _click_ok(dialog)
    logger.info("기존 폴더 선택 완료: %s", folder_name)


def _create_new_folder_and_confirm(dlg, folder_name: str) -> None:
    """팝업 안에서 새 폴더를 만들고, 생성된 폴더를 실제 선택한 뒤 확인한다."""
    dialog = _connect_dialog(dlg)
    try:
        _create_new_folder_and_confirm_uia(dialog, folder_name)
    except Exception:
        logger.warning("UIA 새 폴더 생성/선택 실패. 키보드 fallback을 시도합니다.", exc_info=True)
        _create_new_folder_and_confirm_keyboard(dialog, folder_name)


def _find_tree_item(dialog, folder_name: str, timeout: int = 5):
    end_time = time.time() + timeout
    while time.time() < end_time:
        target = None
        try:
            target = dialog.child_window(title=folder_name, control_type="TreeItem")
            if target.exists(timeout=0.5):
                return target
        except Exception:
            target = None

        try:
            for item in dialog.descendants(control_type="TreeItem"):
                try:
                    if item.window_text() == folder_name:
                        return item
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"생성된 프로젝트 폴더 TreeItem을 찾을 수 없습니다: {folder_name}")


def _select_tree_item(target, folder_name: str) -> None:
    """TreeItem을 실제 마우스 입력으로 선택한다."""
    try:
        target.ensure_visible()
    except Exception:
        pass

    try:
        target.click_input()
    except Exception:
        target.select()
    time.sleep(0.5)

    try:
        if hasattr(target, "is_selected") and not target.is_selected():
            target.click_input()
            time.sleep(0.3)
    except Exception:
        logger.debug("폴더 TreeItem 선택 상태 확인 실패: %s", folder_name, exc_info=True)


def _click_ok(dialog) -> None:
    ok_btn = dialog.child_window(title="확인", control_type="Button")
    if not ok_btn.exists(timeout=2):
        ok_btn = dialog.child_window(title="OK", control_type="Button")
    try:
        ok_btn.click_input()
    except Exception:
        send_keys("{ENTER}")


def _create_new_folder_and_confirm_uia(dialog, folder_name: str) -> None:
    """UIA control tree를 사용해 새 폴더를 만들고 확인한다."""

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

    new_folder_btn.click_input()
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

    try:
        edit.click_input()
    except Exception:
        pass

    try:
        edit.set_text(folder_name)
    except Exception:
        send_keys("^a{BACKSPACE}")
        send_keys(folder_name, with_spaces=True)
    time.sleep(0.3)

    # Enter 키로 폴더명 확정
    send_keys("{ENTER}")
    time.sleep(0.8)

    target = _find_tree_item(dialog, folder_name, timeout=5)
    _select_tree_item(target, folder_name)
    _click_ok(dialog)
    logger.info("새 폴더 생성 및 선택 완료: %s", folder_name)


def _create_new_folder_and_confirm_keyboard(dialog, folder_name: str) -> None:
    """키보드 조작으로 새 폴더를 만들고 생성된 폴더를 선택한다."""
    try:
        dialog.set_focus()
    except Exception:
        pass

    send_keys("%m")
    time.sleep(0.7)
    send_keys("^a{BACKSPACE}")
    send_keys(folder_name, with_spaces=True)
    time.sleep(0.2)
    send_keys("{ENTER}")
    time.sleep(0.8)

    target = _find_tree_item(dialog, folder_name, timeout=5)
    _select_tree_item(target, folder_name)
    _click_ok(dialog)
    logger.info("키보드 fallback으로 새 폴더 생성 및 선택 완료: %s", folder_name)


def _select_existing_folder_keyboard(dialog, folder_name: str) -> None:
    """UIA click이 COM 오류를 내는 환경을 위한 키보드 fallback."""
    try:
        dialog.set_focus()
    except Exception:
        pass

    target = _find_tree_item(dialog, folder_name, timeout=5)
    _select_tree_item(target, folder_name)
    _click_ok(dialog)
    logger.info("키보드 fallback으로 기존 폴더 선택 시도 완료: %s", folder_name)


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
