import os
import re
import sys
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook, Workbook
from playwright.sync_api import sync_playwright

# Windows UI Automation
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "main" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = DATA_DIR / "weekly_gs_sync.log"
REFERENCE_SHEET_NAME = "인증획득제품리스트"


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


def _env_optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _default_python_executable() -> Path:
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT.parent / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT.parent / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


# =========================
# 설정
# =========================
@dataclass
class Config:
    # ===== 테스트용 (끝나면 False로 바꾸거나 지우면 됨) =====
    test_click_doc_enabled = False

    project_root: Path = PROJECT_ROOT

    # 기준 파일(이제 xlsx로 관리)
    master_xlsx: Path = _env_path("GSCERT_REFERENCE_XLSX", DATA_DIR / "reference.xlsx")

    # 다운로드 폴더
    download_folder: Path = _env_path("GSCERT_WEEKLY_DOWNLOAD_DIR", Path(r"C:\Users\Administrator"))

    # 특정 주차를 수동 갱신할 때 사용한다. 예: 20260511
    target_monday: str = os.environ.get("GSCERT_WEEKLY_TARGET_DATE", "").strip()

    # 이미 받은 xlsx를 직접 기준 파일에 반영할 때 사용한다.
    source_xlsx: Path | None = _env_optional_path("GSCERT_WEEKLY_SOURCE_XLSX")

    # 시작 URL
    start_url: str = os.environ.get("GSCERT_WEEKLY_START_URL", "http://210.104.181.10")

    # 로그인 세션 저장(최초 1회 로그인 후 자동 재사용)
    storage_state: Path = _env_path("GSCERT_EDM_STORAGE_STATE", DATA_DIR / "edm_storage_state.json")

    # reference.xlsx -> PostgreSQL 적재
    python_executable: Path = _env_path("GSCERT_PYTHON", _default_python_executable())
    manage_py: Path = _env_path("GSCERT_MANAGE_PY", PROJECT_ROOT / "manage.py")
    django_settings: str = os.environ.get("GSCERT_DJANGO_SETTINGS", "myproject.settings")

    # 타임아웃/대기
    pw_timeout_ms: int = 30_000
    dialog_wait_sec: int = 15
    download_wait_sec: int = 180

    # 트리/문서 규칙
    year_folder_suffix: str = "시험서비스"
    zero_folder_prefix_re: re.Pattern = re.compile(r"^00\s")
    doc_prefix: str = "인증획득제품"

CFG = Config()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")],
)

class _StreamToLogger:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self._buf = ""

    def write(self, message):
        if not message:
            return
        self._buf += message
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if line:
                self.logger.log(self.level, line)

    def flush(self):
        if self._buf.strip():
            self.logger.log(self.level, self._buf.strip())
        self._buf = ""

# stdout/stderr를 logging으로 흡수 (print/traceback 포함)
_root = logging.getLogger()
sys.stdout = _StreamToLogger(_root, logging.INFO)
sys.stderr = _StreamToLogger(_root, logging.ERROR)
    

# =========================
# 공통 유틸
# =========================
def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _reference_sheet(wb):
    if REFERENCE_SHEET_NAME in wb.sheetnames:
        return wb[REFERENCE_SHEET_NAME]
    return wb.active


# =========================
# 날짜(전 주 월요일)
# =========================
def this_week_monday_yyyymmdd(tz: str = "Asia/Seoul") -> str:
    target_monday = resolve_target_monday_arg()
    if target_monday:
        try:
            datetime.strptime(target_monday, "%Y%m%d")
        except ValueError as exc:
            raise ValueError("대상 날짜는 YYYYMMDD 형식이어야 합니다.") from exc
        return target_monday

    now = datetime.now(ZoneInfo(tz))
    monday = now - timedelta(days=now.weekday()) - timedelta(days=7)
    return monday.strftime("%Y%m%d")


def resolve_target_monday_arg() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    return CFG.target_monday


# =========================
# 기준 파일(xlsx) 처리
# =========================
def read_last_serial_from_master_xlsx(xlsx_path: Path) -> int:
    """
    reference.xlsx에서 A열(일련번호) 마지막 숫자를 robust하게 찾는다.
    - A열을 아래에서 위로 훑으며 가장 마지막 숫자(정수)를 반환
    """
    if not xlsx_path.exists():
        raise FileNotFoundError(f"master file not found: {xlsx_path}")

    wb = load_workbook(xlsx_path, data_only=True)
    ws = _reference_sheet(wb)

    for r in range(ws.max_row, 0, -1):
        v = ws.cell(row=r, column=1).value
        if v is None:
            continue
        s = str(v).strip().strip('"').strip("'")
        m = re.fullmatch(r"(\d+)(?:\.0+)?", s)
        if m:
            return int(m.group(1))

    raise ValueError("A열(일련번호)에서 마지막 숫자를 찾지 못했습니다. (xlsx)")


def append_rows_to_master_xlsx(master_xlsx: Path, rows: list[list], ensure_14_cols: bool = True) -> None:
    """
    master.xlsx 마지막 행 다음에 A~N(14컬럼) 값을 append.
    줄바꿈(\n) 포함 문자열은 그대로 셀에 들어감.
    """
    master_xlsx.parent.mkdir(parents=True, exist_ok=True)

    if master_xlsx.exists():
        wb = load_workbook(master_xlsx)
    else:
        wb = Workbook()

    ws = _reference_sheet(wb)

    # 마지막 "의미 있는" 행 찾기: A열이 비어있지 않은 마지막 행 기준
    last = ws.max_row
    while last > 1 and _is_blank(ws.cell(row=last, column=1).value):
        last -= 1
    write_row = last + 1

    for row in rows:
        if ensure_14_cols:
            row = (row + [None] * 14)[:14]

        for c_idx in range(1, 15):  # 1..14 (A..N)
            v = row[c_idx - 1]
            ws.cell(row=write_row, column=c_idx, value=v)
        write_row += 1

    wb.save(master_xlsx)


# =========================
# 다운로드 xlsx에서 범위 추출
# =========================
def extract_a_to_n_rows_after_serial(xlsx_path: Path, start_serial: int, sheet_name: str | None = None) -> list[list]:
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")

    target_sheet = sheet_name or REFERENCE_SHEET_NAME
    wb = load_workbook(xlsx_path, data_only=True)
    if target_sheet not in wb.sheetnames:
        raise ValueError(f"시트 '{target_sheet}' 를 찾지 못했습니다. 현재 시트: {wb.sheetnames}")
    ws = wb[target_sheet]

    found_row = None
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, (int, float)) and int(v) == int(start_serial):
            found_row = r
            break
        if isinstance(v, str) and v.strip().isdigit() and int(v.strip()) == int(start_serial):
            found_row = r
            break

    if found_row is None:
        raise ValueError(f"다운로드 엑셀 A열에서 일련번호 {start_serial} 를 찾지 못했습니다.")

    start_row = found_row + 1

    last_data_row = 0
    for r in range(1, ws.max_row + 1):
        any_val = False
        for c in range(1, 15):  # A..N
            if ws.cell(row=r, column=c).value not in (None, ""):
                any_val = True
                break
        if any_val:
            last_data_row = r

    if last_data_row < start_row:
        return []

    out = []
    for r in range(start_row, last_data_row + 1):
        vals = [ws.cell(row=r, column=c).value for c in range(1, 15)]
        if all(v in (None, "") for v in vals):
            continue
        out.append(vals)
    return out


# =========================
# 행 정규화(요청사항 반영)
# =========================
def normalize_rows(rows: list[list]) -> list[list]:
    """
    요청 반영 규칙:

    (1) 추가 기업명 행 합치기:
        - 조건: A 비어있고 AND C 비어있고 AND D 존재
        - 동작: 바로 위 행 D에 '\\n' + D를 붙이고 현재 행은 삭제

    (2) A만 비어있는 경우 삭제:
        - 조건: A 비어있고 AND (B 또는 C 값이 존재)
        - 동작: 현재 행은 삭제

    주의: (1)이 (2)보다 먼저 평가되어야 함.
    """
    out: list[list] = []

    for row in rows:
        row = (row + [None] * 14)[:14]  # A..N 고정

        # 완전 빈 행 제거
        if all(_is_blank(v) for v in row):
            continue

        a = row[0]  # A: 일련번호
        b = row[1]  # B: 인증번호
        c = row[2]  # C: 인증일자
        d = row[3]  # D: 회사명

        # (1) 추가 기업명 행 합치기: A blank & C blank & D has value
        if _is_blank(a) and _is_blank(c) and not _is_blank(d) and out:
            prev = out[-1]
            prev_d = "" if _is_blank(prev[3]) else str(prev[3]).strip()
            cur_d = str(d).strip()
            # 줄바꿈 유지
            out[-1][3] = (prev_d + "\n" + cur_d).strip()
            continue  # 현재 행 삭제

        # (2) A blank & (B or C has value) => 삭제
        if _is_blank(a) and (not _is_blank(b) or not _is_blank(c)):
            continue

        out.append(row)

    return out


# =========================
# UIA: "폴더 찾아보기" 대화상자 처리 (Enter만)
# =========================
def confirm_browse_dialog_by_enter(wait_popup_sec: int = 15, after_popup_sec: float = 3.0):
    """
    '폴더 찾아보기' 팝업이 뜬 뒤 after_popup_sec(기본 3초) 기다렸다가 Enter만 눌러 진행.
    - 기본 폴더/최근 폴더가 이미 원하는 경로로 선택되어 있다는 전제
    """
    # 1) 팝업이 뜰 때까지 최대 wait_popup_sec 동안 기다림 (Win32로 가볍게 체크)
    dlg = None
    end = time.time() + max(1, int(wait_popup_sec))
    while time.time() < end:
        try:
            cand = Desktop(backend="win32").window(title="폴더 찾아보기", class_name="#32770")
            if cand.exists(timeout=0.2):
                dlg = cand
                break
        except Exception:
            pass
        time.sleep(0.2)

    # 2) 팝업이 확인되면 포커스 주고(가능하면), 3초 기다렸다가 Enter
    if dlg is not None:
        try:
            dlg.set_focus()
        except Exception:
            pass

    logging.info("폴더 선택 팝업 대기 후 Enter 입력: %.1fs", after_popup_sec)
    time.sleep(max(0.0, float(after_popup_sec)))

    send_keys("{ENTER}")


# =========================
# 다운로드 완료 대기(파일 생성 + 크기 안정화)
# =========================
def wait_for_file_complete(folder: Path, expected_name: str, timeout_sec: int) -> Path:
    folder = folder.resolve()
    end = time.time() + timeout_sec
    target = folder / expected_name

    last_size = -1
    stable_count = 0

    while time.time() < end:
        if target.exists():
            try:
                size = target.stat().st_size
            except OSError:
                time.sleep(0.3)
                continue

            if size == last_size and size > 0:
                stable_count += 1
            else:
                stable_count = 0
            last_size = size

            if stable_count >= 3:
                return target

        time.sleep(0.5)

    raise TimeoutError(f"다운로드 파일이 완료되지 않았습니다: {target}")


# =========================
# Playwright: 웹 탐색/저장 트리거
# =========================
def ensure_page(p):
    browser = p.chromium.launch(headless=False)  # UI 팝업 때문에 headful 필수
    context_kwargs = {
        "accept_downloads": False,  # 브라우저 다운로드가 아니라 OS 팝업 방식이라 의미 없음
        "viewport": {"width": 1400, "height": 900},
    }
    if CFG.storage_state.exists():
        context_kwargs["storage_state"] = str(CFG.storage_state)

    ctx = browser.new_context(**context_kwargs)
    page = ctx.new_page()
    page.set_default_timeout(CFG.pw_timeout_ms)

    page.goto(CFG.start_url, wait_until="domcontentloaded")

    if not CFG.storage_state.exists():
        logging.warning("처음 실행: 브라우저에서 로그인/SSO 완료 후 Enter를 누르세요.")
        input("로그인 완료 후 Enter: ")
        ctx.storage_state(path=str(CFG.storage_state))
        logging.info("storage_state 저장 완료: %s", CFG.storage_state)

    return browser, ctx, page


def click_year_and_first_00_folder(page, year: int):
    from playwright.sync_api import TimeoutError as PWTimeout

    year_text = f"{year} {CFG.year_folder_suffix}"
    logging.info("연도 폴더 클릭: %s", year_text)

    page.locator('a[menuname="edm-folder-context-tree"]').first.wait_for(state="visible", timeout=60_000)

    year_a = page.locator(
        'a[menuname="edm-folder-context-tree"]',
        has_text=re.compile(rf"^\s*{year}\s*{re.escape(CFG.year_folder_suffix)}\s*$")
    ).first

    year_a.scroll_into_view_if_needed()
    year_a.click()
    page.wait_for_timeout(300)

    year_li = year_a.locator("xpath=ancestor::li[1]")

    cls = (year_li.get_attribute("class") or "")
    if "jstree-closed" in cls:
        expander = year_li.locator("ins.jstree-icon").first
        expander.click()
        page.wait_for_function(
            """(el) => (el.className || '').includes('jstree-open')""",
            arg=year_li,
            timeout=60_000
        )
    else:
        try:
            page.wait_for_function(
                """(el) => (el.querySelectorAll('ul li a[menuname="edm-folder-context-tree"]').length > 0)""",
                arg=year_li,
                timeout=10_000
            )
        except Exception:
            pass

    zero_a = year_li.locator('a[menuname="edm-folder-context-tree"]').filter(
        has_text=re.compile(r"^\s*00\s")
    ).first

    try:
        zero_a.wait_for(state="visible", timeout=60_000)
    except PWTimeout:
        zero_a = page.locator('a[menuname="edm-folder-context-tree"]').filter(
            has_text=re.compile(rf"^\s*00\s+{year}년")
        ).first
        zero_a.wait_for(state="visible", timeout=60_000)

    zero_name = zero_a.inner_text()
    logging.info("00 폴더 클릭: %s", zero_name)

    zero_a.scroll_into_view_if_needed()
    zero_a.click()
    page.wait_for_timeout(800)


def open_doc_properties_by_monday(page, monday: str):
    doc_title = f"{CFG.doc_prefix}({monday})"
    logging.info("문서 클릭: %s", doc_title)
    page.locator("span.document-list-item-name-text-span", has_text=doc_title).first.click()
    page.wait_for_timeout(900)


def trigger_save_icon_for_attachment(page, monday: str):
    filename = f"{CFG.doc_prefix}({monday}).xlsx"
    logging.info("첨부파일 저장 아이콘 클릭(폴더 선택 팝업 유발): %s", filename)

    row = page.locator('tr.prop-view-file-list-item', has_text=filename).first
    save_btn = row.locator('div[events="document-fileSave-click"]').first
    save_btn.click()


def sync_reference_db():
    import subprocess

    if not CFG.manage_py.exists():
        raise FileNotFoundError(f"manage.py 파일을 찾을 수 없습니다: {CFG.manage_py}")

    cmd = [
        str(CFG.python_executable),
        str(CFG.manage_py),
        "import_reference_db",
        "--source-xlsx",
        str(CFG.master_xlsx),
        "--settings",
        CFG.django_settings,
    ]

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    logging.info("reference PostgreSQL 적재 실행: %s", " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=str(CFG.project_root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.stdout.strip():
        logging.info("reference DB 적재 stdout: %s", completed.stdout.strip())
    if completed.stderr.strip():
        logging.error("reference DB 적재 stderr: %s", completed.stderr.strip())
    if completed.returncode != 0:
        raise RuntimeError(f"reference DB 적재 실패: exit_code={completed.returncode}")

    logging.info("reference PostgreSQL DB 적재 완료")


# =========================
# main
# =========================
def main():
    CFG.download_folder.mkdir(parents=True, exist_ok=True)

    # 1) 기준 파일 A열 마지막 숫자
    last_serial = read_last_serial_from_master_xlsx(CFG.master_xlsx)
    logging.info("master 마지막 일련번호(A열): %s", last_serial)

    # 2) 이번주 월요일 파일명 결정
    monday = this_week_monday_yyyymmdd()
    if getattr(CFG, "test_click_doc_enabled", False):
        monday = "20260105"  # 테스트 끝나면 이 블록 삭제하거나 False로
        logging.info("[TEST] monday 강제 설정: %s", monday)
    if resolve_target_monday_arg():
        logging.info("대상 주차 수동 지정: %s", monday)

    xlsx_name = f"{CFG.doc_prefix}({monday}).xlsx"
    expected_path = CFG.download_folder / xlsx_name

    if CFG.source_xlsx:
        downloaded = CFG.source_xlsx
        if not downloaded.exists():
            raise FileNotFoundError(f"GSCERT_WEEKLY_SOURCE_XLSX 파일을 찾을 수 없습니다: {downloaded}")
        logging.info("다운로드 단계 생략, 지정된 xlsx 사용: %s", downloaded)
    else:
        if expected_path.exists():
            try:
                expected_path.unlink()
            except Exception:
                pass

        year = int(monday[:4])

        # 3) 웹에서 저장 트리거 + 폴더 선택 팝업 처리 + 파일 생성 대기
        with sync_playwright() as p:
            browser, ctx, page = ensure_page(p)
            try:
                click_year_and_first_00_folder(page, year)
                open_doc_properties_by_monday(page, monday)

                trigger_save_icon_for_attachment(page, monday)

                # 폴더 찾아보기 팝업: 2~3초 후 Enter면 충분하다고 했으니 그대로 반영
                confirm_browse_dialog_by_enter(wait_popup_sec=CFG.dialog_wait_sec, after_popup_sec=3.0)

                downloaded = wait_for_file_complete(CFG.download_folder, xlsx_name, timeout_sec=CFG.download_wait_sec)
                logging.info("다운로드 완료 확인: %s", downloaded)

            finally:
                ctx.close()
                browser.close()

    # 4) xlsx에서 last_serial 아래부터 A~N 추출 -> 정규화 -> master.xlsx append
    logging.info("추가분 추출 대상 xlsx: %s", downloaded)
    rows = extract_a_to_n_rows_after_serial(downloaded, start_serial=last_serial, sheet_name="인증획득제품리스트")
    logging.info("추출된 행 수(A~N, 정규화 전): %d", len(rows))

    if rows:
        rows2 = normalize_rows(rows)
        logging.info("정규화 후 행 수(A~N): %d", len(rows2))

        if rows2:
            append_rows_to_master_xlsx(CFG.master_xlsx, rows2, ensure_14_cols=True)
            logging.info("master append 완료(xlsx): %s", CFG.master_xlsx)
        else:
            logging.info("정규화 결과 추가할 데이터가 없습니다. master 변경 없음.")
    else:
        logging.info("추가할 데이터가 없습니다. master 변경 없음.")

    # 5) 저장소 기준 DB 적재
    sync_reference_db()

    logging.info("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("UNHANDLED ERROR")
        raise
