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

# --- 다운로드 파일 기록 완료 대기 (전송현황 창 감지 보완) ---
# DestinyECM 전송은 백그라운드에서 진행되며, 전송현황 창 감지에 실패하면
# 파일이 채 기록되기 전에 검증이 실행되어 0개로 실패할 수 있다.
# 파일시스템을 직접 폴링하여 파일이 생성되고 크기가 안정화될 때까지 기다린다.
DOWNLOAD_FILE_WAIT = 300        # 파일이 안정화될 때까지 최대 대기(초)
DOWNLOAD_POLL_INTERVAL = 2      # 폴링 간격(초)
DOWNLOAD_STABLE_CHECKS = 2      # 크기/개수가 연속으로 동일해야 하는 횟수
DOWNLOAD_PARTIAL_SUFFIXES = (".tmp", ".crdownload", ".part", ".download", ".filepart")


@dataclass
class PopupResult:
    success: bool
    download_dir: str = ""
    error_step: str = ""
    error_message: str = ""
    had_duplicate_alert: bool = False


def _download_base_dir() -> str:
    return getattr(settings, "AGENT_DOWNLOAD_BASE_DIR", r"C:\Users\Administrator\ecm")


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
        _navigate_to_ecm_and_create_folder(folder_dlg, folder_name)
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

    # Step 4: 다운로드 파일이 실제로 기록 완료될 때까지 대기.
    # 전송현황 창 감지가 실패해도 파일시스템을 직접 관찰하므로 신뢰할 수 있다.
    if not _wait_for_download_files(download_dir):
        return PopupResult(
            success=False,
            download_dir=download_dir,
            error_step="다운로드 파일 대기",
            error_message=f"다운로드 파일이 {DOWNLOAD_FILE_WAIT}초 내에 생성/안정화되지 않았습니다: {download_dir}",
        )

    return PopupResult(success=True, download_dir=download_dir)


def _list_download_files(download_dir: str) -> list:
    """다운로드 폴더의 일반 파일 이름 목록을 반환한다."""
    try:
        return [
            name for name in os.listdir(download_dir)
            if os.path.isfile(os.path.join(download_dir, name))
        ]
    except OSError:
        return []


def _wait_for_download_files(download_dir: str) -> bool:
    """다운로드 폴더에 파일이 생성되고 크기가 안정화될 때까지 대기한다.

    전송현황 창 감지에 의존하지 않고 파일시스템을 직접 관찰한다.
    - 부분 다운로드 파일(.tmp/.crdownload 등)이 남아있으면 미완료로 본다.
    - (파일 개수, 총 크기)가 DOWNLOAD_STABLE_CHECKS회 연속 동일하면 완료로 판단한다.

    Returns:
        True: 안정된 파일이 1개 이상 존재.
        False: 시간 초과.
    """
    end_time = time.time() + DOWNLOAD_FILE_WAIT
    last_signature = None
    stable_count = 0

    while time.time() < end_time:
        files = _list_download_files(download_dir)
        has_partial = any(
            name.lower().endswith(DOWNLOAD_PARTIAL_SUFFIXES) for name in files
        )
        complete_files = [
            name for name in files
            if not name.lower().endswith(DOWNLOAD_PARTIAL_SUFFIXES)
        ]
        total_size = 0
        for name in complete_files:
            try:
                total_size += os.path.getsize(os.path.join(download_dir, name))
            except OSError:
                pass

        signature = (len(complete_files), total_size)
        if complete_files and not has_partial and total_size > 0:
            if signature == last_signature:
                stable_count += 1
                if stable_count >= DOWNLOAD_STABLE_CHECKS:
                    logger.info(
                        "다운로드 파일 안정화 확인: %d개, %d bytes (%s)",
                        len(complete_files), total_size, download_dir,
                    )
                    return True
            else:
                stable_count = 0
        else:
            stable_count = 0

        last_signature = signature
        time.sleep(DOWNLOAD_POLL_INTERVAL)

    logger.warning(
        "다운로드 파일 대기 시간 초과(%ds): %s (마지막 상태=%s)",
        DOWNLOAD_FILE_WAIT, download_dir, last_signature,
    )
    return False



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


def _send_vk_to_hwnd(hwnd: int, vk: int) -> None:
    """AttachThreadInput + SendMessageW로 특정 HWND에 키 이벤트를 전달한다.
    전역 포커스 불필요 — SendInput/send_keys 대체용."""
    import ctypes
    import win32con
    import win32api
    import win32process

    my_tid = win32api.GetCurrentThreadId()
    target_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
    attached = (my_tid != target_tid)
    if attached:
        ctypes.windll.user32.AttachThreadInput(my_tid, target_tid, True)
    try:
        ctypes.windll.user32.SetFocus(hwnd)
        time.sleep(0.05)
        ctypes.windll.user32.SendMessageW(hwnd, win32con.WM_KEYDOWN, vk, 0)
        time.sleep(0.05)
        ctypes.windll.user32.SendMessageW(hwnd, win32con.WM_KEYUP, vk, 0xC0000001)
    finally:
        if attached:
            ctypes.windll.user32.AttachThreadInput(my_tid, target_tid, False)


def _find_child_hwnd_by_class(root_hwnd: int, class_name: str) -> int:
    """root_hwnd 하위 전체 계층에서 class_name 창을 찾아 첫 번째 HWND를 반환한다.
    FindWindowEx는 직접 자식만 탐색하므로, EnumChildWindows로 재귀 탐색한다."""
    import win32gui
    found = []

    def _cb(hwnd, _):
        try:
            if win32gui.GetClassName(hwnd) == class_name:
                found.append(hwnd)
                return False  # 첫 번째 발견 즉시 중단
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(root_hwnd, _cb, None)
    except Exception:
        pass
    return found[0] if found else 0


def _navigate_to_ecm_and_create_folder(dlg, folder_name: str) -> None:
    """ecm 폴더로 이동한 뒤 프로젝트 폴더를 생성하고 확인한다.

    send_keys(SendInput)는 전역 포커스에 의존하므로, Chromium 창이 포커스를 가져가면
    키 입력이 실패한다. 대신 AttachThreadInput + SetFocus + SendMessage를 사용해
    포커스에 무관하게 트리 컨트롤에 직접 키 메시지를 전달한다.

    조작 순서:
    1. SysTreeView32 HWND 획득 (EnumChildWindows 재귀 탐색)
    2. AttachThreadInput으로 다이얼로그 스레드에 연결 → SetFocus(tree)
    3. Home → Down → Right → 'e' (ecm 폴더)
    4. 새 폴더(folder_name) 생성 후 확인
    """
    import ctypes
    import win32gui
    import win32api
    import win32process
    import win32con

    # FindWindowEx는 직접 자식만 탐색 → EnumChildWindows 재귀 탐색 사용
    tree_hwnd = _find_child_hwnd_by_class(dlg.handle, "SysTreeView32")
    if not tree_hwnd:
        # dlg.handle이 실제 #32770이 아닌 부모일 수 있으므로 한 단계 위도 시도
        parent_hwnd = win32gui.GetParent(dlg.handle)
        if parent_hwnd:
            tree_hwnd = _find_child_hwnd_by_class(parent_hwnd, "SysTreeView32")
    if not tree_hwnd:
        children_info = []
        def _enum_cb(hwnd, _):
            try:
                children_info.append(f"{win32gui.GetClassName(hwnd)}({hwnd})")
            except Exception:
                pass
            return True
        try:
            win32gui.EnumChildWindows(dlg.handle, _enum_cb, None)
        except Exception:
            pass
        raise RuntimeError(
            f"SysTreeView32를 찾을 수 없습니다. dlg.handle={dlg.handle}, "
            f"children={children_info[:20]}"
        )

    my_tid = win32api.GetCurrentThreadId()
    target_tid, _ = win32process.GetWindowThreadProcessId(tree_hwnd)
    attached = (my_tid != target_tid)
    if attached:
        ctypes.windll.user32.AttachThreadInput(my_tid, target_tid, True)
    try:
        ctypes.windll.user32.SetFocus(tree_hwnd)
        time.sleep(0.2)

        # Home → Down → Right: SendMessage로 트리 탐색 (포커스 불필요)
        for vk in (win32con.VK_HOME, win32con.VK_DOWN, win32con.VK_RIGHT):
            ctypes.windll.user32.SendMessageW(tree_hwnd, win32con.WM_KEYDOWN, vk, 0)
            time.sleep(0.15)
            ctypes.windll.user32.SendMessageW(tree_hwnd, win32con.WM_KEYUP, vk, 0xC0000001)
            time.sleep(0.2)

        # 'e' → WM_KEYDOWN+WM_CHAR+WM_KEYUP 세트로 type-ahead 탐색 (ecm 폴더)
        # WM_CHAR만으로는 TreeView type-ahead가 작동하지 않는 경우가 있음
        VK_E = 0x45
        ctypes.windll.user32.SendMessageW(tree_hwnd, win32con.WM_KEYDOWN, VK_E, 0)
        time.sleep(0.1)
        ctypes.windll.user32.SendMessageW(tree_hwnd, win32con.WM_CHAR, ord('e'), 0)
        time.sleep(0.1)
        ctypes.windll.user32.SendMessageW(tree_hwnd, win32con.WM_KEYUP, VK_E, 0xC0000001)
        time.sleep(0.8)  # type-ahead 결과 반영 대기
    finally:
        if attached:
            ctypes.windll.user32.AttachThreadInput(my_tid, target_tid, False)

    logger.info("트리 직접 포커스로 ecm 폴더 이동 완료. 새 폴더 생성: %s", folder_name)

    # ecm 폴더 안에 새 폴더 생성 후 확인
    _create_new_folder_and_confirm(dlg, folder_name)


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


def _find_button_hwnd_by_text(root_hwnd: int, texts: list) -> int:
    """root_hwnd 하위에서 지정 텍스트를 포함하는 Button HWND를 반환한다."""
    import win32gui
    found = []
    keywords = [t.lower() for t in texts]

    def _cb(hwnd, _):
        try:
            if win32gui.GetClassName(hwnd) == "Button":
                label = win32gui.GetWindowText(hwnd).lower()
                if any(kw in label for kw in keywords):
                    found.append(hwnd)
                    return False
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(root_hwnd, _cb, None)
    except Exception:
        pass
    return found[0] if found else 0


def _click_ok(dialog) -> None:
    import ctypes
    BM_CLICK = 0x00F5
    ok_hwnd = _find_button_hwnd_by_text(dialog.handle, ["확인", "OK"])
    if ok_hwnd:
        ctypes.windll.user32.SendMessageW(ok_hwnd, BM_CLICK, 0, 0)
        return
    # fallback: pywinauto click_input (마우스 클릭)
    ok_btn = dialog.child_window(title="확인", control_type="Button")
    if not ok_btn.exists(timeout=2):
        ok_btn = dialog.child_window(title="OK", control_type="Button")
    ok_btn.click_input()


def _create_new_folder_and_confirm_uia(dialog, folder_name: str) -> None:
    """Win32 직접 호출로 새 폴더를 만들고 확인한다.

    pywinauto UIA의 edit.handle이 0을 반환하는 문제를 피하기 위해
    BM_CLICK / TVM_GETEDITCONTROL / SetWindowTextW 를 직접 사용한다.
    """
    import ctypes
    import win32con

    TVM_GETEDITCONTROL = 0x110F
    BM_CLICK = 0x00F5

    dlg_hwnd = dialog.handle
    tree_hwnd = _find_child_hwnd_by_class(dlg_hwnd, "SysTreeView32")
    if not tree_hwnd:
        raise RuntimeError("SysTreeView32를 찾을 수 없습니다.")

    # '새 폴더 만들기' 버튼 — win32 BM_CLICK (포커스·SendInput 불필요)
    btn_hwnd = _find_button_hwnd_by_text(dlg_hwnd, ["새 폴더 만들기"])
    if not btn_hwnd:
        raise RuntimeError("'새 폴더 만들기' 버튼을 찾을 수 없습니다.")
    ctypes.windll.user32.SendMessageW(btn_hwnd, BM_CLICK, 0, 0)
    time.sleep(0.5)

    # TVM_GETEDITCONTROL: TreeView가 관리하는 인라인 편집 HWND 획득
    edit_hwnd = 0
    for _ in range(20):
        edit_hwnd = ctypes.windll.user32.SendMessageW(tree_hwnd, TVM_GETEDITCONTROL, 0, 0)
        if edit_hwnd:
            break
        time.sleep(0.2)

    if not edit_hwnd:
        raise RuntimeError("TreeView 인라인 편집창(TVM_GETEDITCONTROL)을 찾을 수 없습니다.")

    # SetWindowTextW는 TreeView 인라인 편집창에 반영되지 않는 경우가 있음.
    # EM_SETSEL로 전체 선택 후 WM_CHAR 문자별 입력으로 대체한다.
    EM_SETSEL = 0x00B1
    ctypes.windll.user32.SendMessageW(edit_hwnd, EM_SETSEL, 0, -1)  # 전체 선택
    time.sleep(0.05)
    for ch in folder_name:
        ctypes.windll.user32.SendMessageW(edit_hwnd, win32con.WM_CHAR, ord(ch), 1)
        time.sleep(0.02)
    time.sleep(0.15)
    logger.info("인라인 편집창에 폴더명 입력 완료: %s", folder_name)
    _send_vk_to_hwnd(edit_hwnd, win32con.VK_RETURN)
    time.sleep(0.8)

    target = _find_tree_item(dialog, folder_name, timeout=5)
    _select_tree_item(target, folder_name)
    _click_ok(dialog)
    logger.info("새 폴더 생성 및 선택 완료: %s", folder_name)


def _create_new_folder_and_confirm_keyboard(dialog, folder_name: str) -> None:
    """UIA 경로 실패 시 fallback — 동일한 win32 직접 호출 방식 재시도."""
    logger.info("keyboard fallback: win32 직접 호출로 재시도")
    _create_new_folder_and_confirm_uia(dialog, folder_name)



def _wait_for_transfer_complete() -> None:
    """전송현황 창이 뜨고 사라질 때까지 대기한다.

    첫 번째 다운로드는 DestinyECM 초기화로 전송현황 창이 늦게 뜰 수 있으므로
    감지 타임아웃을 넉넉히 60초로 설정한다.
    창이 닫힌 후에도 파일이 디스크에 기록 완료될 때까지 잠시 대기한다.
    """
    logger.info("전송현황 창 대기 중...")
    transfer_dlg = _wait_for_window(TRANSFER_STATUS_TITLE, timeout=60)
    if transfer_dlg is None:
        logger.info("전송현황 창이 60초 내에 표시되지 않았습니다. 이미 완료되었거나 매우 빠르게 처리됐을 수 있습니다.")
        time.sleep(5)  # 파일 기록 완료 대기
        return

    logger.info("전송현황 창 감지됨. 다운로드 완료 대기 중...")
    end_time = time.time() + TRANSFER_WAIT
    while time.time() < end_time:
        desktop = Desktop(backend="uia")
        windows = desktop.windows(title=TRANSFER_STATUS_TITLE)
        if not windows:
            logger.info("전송현황 창이 사라졌습니다. 다운로드 완료.")
            time.sleep(3)  # 파일 기록 완료 대기 (전송현황 닫힌 후 디스크 동기화)
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
