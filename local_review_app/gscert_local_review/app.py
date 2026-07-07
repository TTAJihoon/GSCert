from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QThread, QSettings, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiClientError, GSCertApiClient, ProjectMetadata, ReferenceItem
from .local_runner import (
    ENGINE_VERSION,
    ERROR,
    FAIL,
    PASS,
    UNSUPPORTED,
    LocalRunSummary,
    engine_supports,
    run_cached_rules,
)
from .project import infer_project_number
from .rule_cache import RuleCacheSummary, load_rule_bundle, load_rule_cache, save_rule_cache
from .scanner import FolderScan, scan_folder


DEFAULT_SERVER_URL = "http://127.0.0.1:8000"

# ── Design tokens (pgAdmin 스타일: 스틸블루 강조 + 조밀/평면 UI) ───────────────
C_BG           = "#ffffff"
C_SURFACE      = "#ffffff"
C_SOFT         = "#f2f4f7"   # 헤더/보조 배경 (쿨 그레이)
C_LINE         = "#c9d0d9"   # 테두리 (pgAdmin처럼 또렷하게)
C_LINE_STRONG  = "#a7b0bd"
C_TEXT         = "#243142"   # 쿨 다크
C_MUTED        = "#6b7683"
C_PRIMARY      = "#326690"   # pgAdmin 시그니처 스틸블루
C_PRIMARY_SOFT = "#e2ecf4"
C_HEADER_BG    = "#e9edf2"   # 상단 툴바 밴드 / 테이블 헤더
C_GRID         = "#dfe4ea"   # 데이터 그리드 선
C_SELECT       = "#d6e6f4"   # 행 선택 하이라이트
C_SUCCESS      = "#067647"
C_SUCCESS_SOFT = "#e7f6ee"
C_WARNING      = "#b54708"
C_WARNING_SOFT = "#fff4e5"
C_DANGER       = "#b42318"
C_DANGER_SOFT  = "#fdecec"
C_FAIL_ROW     = "#eef1f4"   # 부적합 세부 항목 행 배경 (밝은 회색)

STATUS_META = {
    PASS:        (C_SUCCESS, C_SUCCESS_SOFT, "적합"),
    FAIL:        (C_DANGER,  C_DANGER_SOFT,  "부적합"),
    UNSUPPORTED: (C_MUTED,   "#eef2f6",      "미지원"),
    ERROR:       (C_WARNING, C_WARNING_SOFT, "오류"),
}

REVIEW_COLOR = {
    "완료":     C_SUCCESS,
    "수정 필요": C_WARNING,
    "보류":     C_MUTED,
}

APP_QSS = f"""
/* ── Base ─────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {C_SOFT};
}}
QWidget {{
    font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: {C_TEXT};
}}

/* ── Scrollbars ────────────────────────────── */
QScrollBar:vertical {{
    width: 12px;
    background: {C_SOFT};
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C_LINE_STRONG};
    border-radius: 2px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    height: 12px;
    background: {C_SOFT};
}}
QScrollBar::handle:horizontal {{
    background: {C_LINE_STRONG};
    border-radius: 2px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Panel cards (평면, 작은 라운드) ─────────── */
QFrame#panel {{
    background-color: {C_SURFACE};
    border: 1px solid {C_LINE};
    border-radius: 4px;
}}

/* ── 상단 헤더 (흰색 패널; 프로그램 배경만 회색) ── */
QFrame#headerBar {{
    background-color: {C_SURFACE};
    border: 1px solid {C_LINE};
    border-radius: 4px;
}}

/* ── Inputs ────────────────────────────────── */
QLineEdit, QComboBox {{
    min-height: 30px;
    padding: 0 8px;
    border: 1px solid {C_LINE};
    border-radius: 3px;
    background-color: {C_SURFACE};
    color: {C_TEXT};
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {C_PRIMARY};
}}
QLineEdit:read-only {{
    background-color: {C_SURFACE};
    color: {C_TEXT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {C_LINE};
    border-radius: 3px;
    background: {C_SURFACE};
    selection-background-color: {C_SELECT};
    selection-color: {C_TEXT};
    outline: none;
}}

/* ── Buttons (평면, 조밀) ───────────────────── */
QPushButton {{
    min-height: 30px;
    padding: 0 12px;
    border: 1px solid {C_LINE_STRONG};
    border-radius: 3px;
    background-color: {C_SURFACE};
    color: {C_TEXT};
    font-weight: 600;
    font-size: 12px;  /* 기본 13px 대비 약 5% 축소 */
}}
QPushButton:hover {{
    background-color: {C_HEADER_BG};
    border-color: {C_PRIMARY};
}}
QPushButton:pressed {{
    background-color: #dde3ea;
}}
QPushButton:disabled {{
    color: #9aa4b0;
    background-color: {C_SOFT};
    border-color: {C_LINE};
}}
QPushButton#primaryBtn {{
    background-color: #0a357f;
    color: #ffffff;
    border: 1px solid #082a66;
    font-weight: 800;
}}
QPushButton#primaryBtn:hover {{
    background-color: #082a66;
    color: #ffffff;
    border: 1px solid #061f4d;
}}
QPushButton#primaryBtn:pressed {{
    background-color: #061f4d;
    color: #ffffff;
    border: 1px solid #061f4d;
}}
QPushButton#primaryBtn:disabled {{
    background-color: #aebfd9;
    color: #eef2fb;
    border: 1px solid #93a6c9;
}}

/* ── Tables (pgAdmin 데이터 그리드) ──────────── */
QTableWidget {{
    background-color: {C_SURFACE};
    border: 1px solid {C_LINE};
    border-radius: 4px;
    gridline-color: {C_GRID};
    selection-background-color: {C_SELECT};
    selection-color: {C_TEXT};
    outline: none;
}}
QTableWidget::item {{
    padding: 4px 8px;
    border-bottom: 1px solid {C_GRID};
    border-right: 1px solid {C_GRID};
}}
QTableWidget::item:selected {{
    background-color: {C_SELECT};
    color: {C_TEXT};
}}
QTableWidget[alternatingRowColors="true"]::item:alternate {{
    background-color: {C_SURFACE};
}}
QHeaderView::section {{
    background-color: {C_SURFACE};
    color: #3a4756;
    font-weight: 700;
    font-size: 12px;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {C_LINE_STRONG};
    border-right: 1px solid {C_LINE};
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableCornerButton::section {{
    background-color: {C_SURFACE};
    border: none;
    border-bottom: 1px solid {C_LINE_STRONG};
}}

/* ── Progress bar (busy indicator) ─────────── */
QProgressBar {{
    border: 1px solid {C_LINE};
    border-radius: 2px;
    background-color: {C_SOFT};
    max-height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {C_PRIMARY};
    border-radius: 2px;
}}

/* ── Status bar (pgAdmin 하단 상태 표시줄) ────── */
QStatusBar {{
    background-color: {C_HEADER_BG};
    border-top: 1px solid {C_LINE_STRONG};
    color: {C_MUTED};
    font-size: 12px;
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{
    color: {C_MUTED};
    background: transparent;
    padding: 0 4px;
}}

/* ── Splitter ──────────────────────────────── */
QSplitter::handle {{
    background-color: {C_LINE};
}}
QSplitter::handle:horizontal {{
    width: 1px;
    margin: 4px 0;
}}
QSplitter::handle:vertical {{
    height: 1px;
    margin: 0 4px;
}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    # objectName 선택자로 이 프레임에만 흰 배경 지정(자식 위젯에는 전파 안 됨).
    f.setStyleSheet(
        f"QFrame#panel {{ background-color: {C_SURFACE};"
        f" border: 1px solid {C_LINE}; border-radius: 4px; }}"
    )
    return f


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    font = lbl.font()
    font.setPointSize(11)
    font.setBold(True)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {C_TEXT}; background: transparent; border: none;")
    return lbl


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {C_MUTED}; font-size: 12px; background: transparent; border: none;")
    return lbl


def _hsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"color: {C_LINE}; background-color: {C_LINE}; border: none; max-height: 1px;")
    return sep


def _vsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet(f"color: {C_LINE}; background-color: {C_LINE}; border: none; max-width: 1px;")
    return sep


def _stat_badge(text: str, fg: str, bg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        background-color: {bg};
        color: {fg};
        border-radius: 10px;
        padding: 2px 10px;
        font-size: 12px;
        font-weight: 700;
        border: none;
    """)
    return lbl


# ── GS 인증 검색 다이얼로그 ──────────────────────────────────────────────────────

class ReferenceSearchDialog(QDialog):
    def __init__(self, client: "GSCertApiClient", parent=None):
        super().__init__(parent)
        self.client = client
        self.selected: ReferenceItem | None = None
        self.setWindowTitle("GS 인증 이력 검색")
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        # Search row
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("회사명, 제품명 또는 GS인증번호로 검색")
        self._search_input.returnPressed.connect(self._do_search)
        search_btn = QPushButton("검색")
        search_btn.setMinimumWidth(72)
        search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self._search_input, stretch=1)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        # Result table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["인증번호", "회사명", "제품명", "인증일자", "GS번호"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.doubleClicked.connect(self._accept_selection)
        layout.addWidget(self._table, stretch=1)

        self._status = _muted("")
        layout.addWidget(self._status)

        # Buttons
        btn_box = QDialogButtonBox()
        self._select_btn = btn_box.addButton("선택", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("닫기", QDialogButtonBox.ButtonRole.RejectRole)
        self._select_btn.clicked.connect(self._accept_selection)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._items: list[ReferenceItem] = []

    def _do_search(self):
        q = self._search_input.text().strip()
        if not q or len(q) < 2:
            self._status.setText("검색어를 2자 이상 입력하세요.")
            return
        try:
            items = self.client.search_reference(q)
        except ApiClientError as exc:
            self._status.setText(f"오류: {exc}")
            return
        self._items = items
        self._populate(items)
        self._status.setText(f"{len(items)}건 검색됨" if items else "검색 결과가 없습니다.")

    def _populate(self, items: list[ReferenceItem]):
        self._table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, val in enumerate([
                item.cert_number,
                item.company,
                item.product,
                item.cert_date,
                item.test_number,
            ]):
                self._table.setItem(row, col, QTableWidgetItem(val))

    def _accept_selection(self):
        rows = self._table.selectedItems()
        if not rows:
            return
        row = self._table.row(rows[0])
        if 0 <= row < len(self._items):
            self.selected = self._items[row]
            self.accept()


class ManualMetadataDialog(QDialog):
    """서버 미연결(오프라인) 등으로 기준정보를 조회할 수 없을 때 수동 입력한다.

    점검은 메타데이터가 반드시 있어야 하므로(컨텍스트 의존 규칙), 온라인은 서버 조회,
    오프라인은 이 직접 입력 경로로 메타데이터를 채운다.
    """

    TEXT_FIELDS = [
        ("company_name", "회사명"),
        ("product_name", "제품명"),
        ("pl_name", "시험PL"),
        ("wd_name", "WD"),
    ]
    # (attr, label, required)
    DATE_FIELDS = [
        ("start_date", "시험 시작일", True),
        ("end_date", "시험 종료일", True),
        ("cert_date", "인증일자", False),
    ]

    def __init__(
        self,
        project_number: str,
        initial: "ProjectMetadata | None" = None,
        prefill: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("기준정보 직접 입력")
        self.setMinimumWidth(440)
        self.result_metadata: ProjectMetadata | None = None
        self._project_number = project_number
        prefill = prefill or {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"프로젝트번호: {project_number or '(미입력)'}"))
        grid = QGridLayout()
        row = 0

        self._edits: dict[str, QLineEdit] = {}
        for attr, label in self.TEXT_FIELDS:
            grid.addWidget(QLabel(label), row, 0)
            edit = QLineEdit()
            value = str(getattr(initial, attr, "") or "") if initial is not None else ""
            if not value:
                value = str(prefill.get(attr, "") or "")
            edit.setText(value)
            grid.addWidget(edit, row, 1)
            self._edits[attr] = edit
            row += 1

        # 날짜는 달력 팝업(QDateEdit)으로 입력한다. 미선택 상태는 최소 날짜로 표시한다.
        self._date_edits: dict[str, tuple[QDateEdit, bool]] = {}
        for attr, label, required in self.DATE_FIELDS:
            grid.addWidget(QLabel(label), row, 0)
            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy.MM.dd")
            date_edit.setMinimumDate(QDate(2000, 1, 1))
            date_edit.setDate(QDate.currentDate())  # 기본값=오늘 → 달력이 오늘 기준으로 열림
            init_value = str(getattr(initial, attr, "") or "") if initial is not None else ""
            parsed = self._parse_date(init_value)
            if parsed is not None:
                date_edit.setDate(parsed)
            grid.addWidget(date_edit, row, 1)
            self._date_edits[attr] = (date_edit, required)
            row += 1

        layout.addLayout(grid)

        hint = QLabel("날짜 칸을 클릭하면 달력에서 선택할 수 있습니다.")
        hint.setStyleSheet(f"color: {C_MUTED}; font-size: 11px; border: none;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _parse_date(text: str) -> "QDate | None":
        """조회된 날짜 문자열을 관대하게 파싱한다.

        구글시트/DB에서 온 값은 "2026.04.15", "2026-04-15", "2026/4/5",
        "2026. 4. 15", "2026년 4월 15일", "2026-04-15 00:00" 등 형식이 제각각이라
        엄격한 QDate 포맷 매칭으로는 실패하고 오늘 날짜로 되돌아가는 문제가 있었다.
        연-월-일 숫자 3개만 뽑아 QDate로 조립한다."""
        text = (text or "").strip()
        if not text:
            return None
        m = re.search(r"(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", text)
        if not m:
            return None
        year, month, day = (int(g) for g in m.groups())
        qd = QDate(year, month, day)
        return qd if qd.isValid() else None

    def _date_value(self, date_edit: QDateEdit) -> str:
        return date_edit.date().toString("yyyy.MM.dd")

    def _accept(self):
        values = {attr: edit.text().strip() for attr, edit in self._edits.items()}
        for attr, (date_edit, _required) in self._date_edits.items():
            values[attr] = self._date_value(date_edit)
        # 시험기간(시작/종료일)은 날짜 규칙에 필수
        if not values.get("start_date") or not values.get("end_date"):
            QMessageBox.warning(self, "기준정보 직접 입력", "시험 시작일과 종료일은 필수입니다.")
            return
        self.result_metadata = ProjectMetadata(project_number=self._project_number, **values)
        self.accept()


# ── 폴더 스캔 백그라운드 워커 ────────────────────────────────────────────────────

class ScanWorker(QThread):
    progress = Signal(int)          # 스캔된 파일 개수
    done = Signal(object)           # FolderScan
    failed = Signal(str)            # 오류 메시지

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self._folder = folder

    def run(self):
        try:
            scan = scan_folder(self._folder, progress_cb=self.progress.emit)
        except Exception as exc:  # noqa: BLE001 - UI에 그대로 전달
            self.failed.emit(str(exc))
            return
        self.done.emit(scan)

class ReviewWorker(QThread):
    done = Signal(object)           # LocalRunSummary
    failed = Signal(str)            # 오류 메시지

    def __init__(self, scan, rule_bundle, project_number, metadata, parent=None):
        super().__init__(parent)
        self._scan = scan
        self._rule_bundle = rule_bundle
        self._project_number = project_number
        self._metadata = metadata

    def run(self):
        try:
            summary = run_cached_rules(
                self._scan,
                self._rule_bundle,
                self._project_number,
                metadata=self._metadata,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.done.emit(summary)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GSCert Local Review")
        self.resize(1300, 840)
        self.selected_folder: Path | None = None
        self.scan: FolderScan | None = None
        self._scan_worker: ScanWorker | None = None
        self._review_worker: ReviewWorker | None = None
        self.current_metadata: ProjectMetadata | None = None
        self.rule_cache = load_rule_cache()
        self._settings = QSettings("TTA", "GSCertLocalReview")

        root = QWidget()
        root.setObjectName("appRoot")
        # objectName 선택자로 root 에만 적용 → 자식 패널로 회색이 전파되지 않는다.
        # (bare background-color 는 자식에 전파되어 패널 흰색을 덮어버린다.)
        root.setStyleSheet(f"QWidget#appRoot {{ background-color: {C_SOFT}; }}")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_controls())
        outer.addWidget(self._build_body(), stretch=1)

        self.setCentralWidget(root)

        # ── 하단 상태 표시줄 (pgAdmin 스타일) ──────────────────────────────
        # 좌측: 현재 동작 상태(액션 상태 미러) / 우측: 서버·규칙 버전 상시 표시.
        self._status_perm = QLabel("")
        self.statusBar().addPermanentWidget(self._status_perm)
        self.statusBar().showMessage("준비")

        self._restore_settings()
        self._refresh_status_perm()
        # 시작 시 서버 규칙 버전을 비교해 stale 규칙을 알린다(오프라인이면 조용히 건너뜀).
        QTimer.singleShot(300, self._check_version_on_startup)

    def _refresh_status_perm(self):
        """상태바 우측에 서버 URL·규칙 버전을 상시 표시한다."""
        server = (self.server_url.text().strip() or DEFAULT_SERVER_URL)
        ver = self.rule_cache.rulebase_version or "규칙 없음"
        self._status_perm.setText(f"서버 {server}   ·   규칙 {ver}")

    def _restore_settings(self):
        saved_url = self._settings.value("server_url", "")
        if saved_url:
            self.server_url.setText(str(saved_url))
        saved_token = self._settings.value("api_token", "")
        if saved_token:
            self.api_token.setText(str(saved_token))
        saved_folder = self._settings.value("last_folder", "")
        if saved_folder and Path(str(saved_folder)).is_dir():
            self.selected_folder = Path(str(saved_folder))
            self.folder_path.setText(str(saved_folder))

    def _save_settings(self):
        self._settings.setValue("server_url", self.server_url.text().strip())
        self._settings.setValue("api_token", self.api_token.text().strip())
        if self.selected_folder is not None:
            self._settings.setValue("last_folder", str(self.selected_folder))

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def _check_version_on_startup(self):
        try:
            manifest = GSCertApiClient(
                self.server_url.text().strip() or DEFAULT_SERVER_URL,
                timeout_seconds=5,
                token=self.api_token.text().strip(),
            ).rule_manifest()
        except Exception:
            return  # 오프라인/서버 오류 → 캐시 규칙으로 계속(조용히 건너뜀)
        server_ver = str(manifest.get("rulebase_version") or "")
        cached_ver = self.rule_cache.rulebase_version or ""
        base_text = self._rule_cache_text(self.rule_cache)
        if server_ver and server_ver != cached_ver:
            self.rulebase_status.setText(f"{base_text}  ⚠ 서버 v{server_ver} 업데이트 있음")
            self._set_action_status("규칙 업데이트 권장", C_WARNING)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QFrame:
        frame = _panel()
        frame.setObjectName("headerBar")  # pgAdmin 스타일 상단 툴바 밴드
        # objectName 을 바꿨으므로 #headerBar 로 흰 배경을 다시 지정한다.
        frame.setStyleSheet(
            f"QFrame#headerBar {{ background-color: {C_SURFACE};"
            f" border: 1px solid {C_LINE}; border-radius: 4px; }}"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 11, 18, 11)
        layout.setSpacing(0)

        # Left: title
        left = QVBoxLayout()
        left.setSpacing(2)
        eyebrow = QLabel("GSCert · ECM 제출물 점검 도구")
        eyebrow.setStyleSheet(
            f"color: {C_MUTED}; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        title = QLabel("GSCert Local Review")
        title.setStyleSheet(
            f"color: {C_TEXT}; font-size: 20px; font-weight: 800;"
            " background: transparent; border: none;"
        )
        left.addWidget(eyebrow)
        left.addWidget(title)

        # Right: server connection
        right = QHBoxLayout()
        right.setSpacing(8)

        url_col = QVBoxLayout()
        url_col.setSpacing(3)
        url_col.addWidget(_muted("서버 URL"))
        self.server_url = QLineEdit(DEFAULT_SERVER_URL)
        self.server_url.setMinimumWidth(220)
        url_col.addWidget(self.server_url)

        # 센터 구분 제거: 센터는 ECM 에이전트(서버) 분리용이었고, 3개 센터의 산출물
        # 구조는 동일하다. 로컬 점검은 폴더/파일 구조만 보므로 센터 선택이 필요 없다.

        token_col = QVBoxLayout()
        token_col.setSpacing(3)
        token_col.addWidget(_muted("API 토큰(선택)"))
        self.api_token = QLineEdit()
        self.api_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_token.setPlaceholderText("서버가 요구할 때만")
        self.api_token.setFixedWidth(140)
        token_col.addWidget(self.api_token)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(3)
        btn_col.addWidget(QLabel(" "))  # spacer to align with labels above
        health_btn = QPushButton("연결 확인")
        health_btn.setMinimumWidth(92)
        health_btn.clicked.connect(self.check_health)
        btn_col.addWidget(health_btn)

        help_col = QVBoxLayout()
        help_col.setSpacing(3)
        help_col.addWidget(QLabel(" "))  # spacer to align with labels above
        help_btn = QPushButton("도움말")
        help_btn.setObjectName("helpBtn")
        help_btn.setMinimumWidth(72)
        help_btn.setToolTip("사용법 보기")
        help_btn.clicked.connect(self._show_help)
        help_col.addWidget(help_btn)

        right.addLayout(url_col)
        right.addLayout(token_col)
        right.addLayout(btn_col)
        right.addLayout(help_col)

        layout.addLayout(left)
        layout.addStretch()
        layout.addLayout(right)
        return frame

    # ── Controls bar ─────────────────────────────────────────────────────────

    def _build_controls(self) -> QFrame:
        frame = _panel()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(0)

        layout.addLayout(self._build_rulebase_section())
        layout.addWidget(_vsep())
        layout.addSpacing(16)
        layout.addLayout(self._build_folder_section(), stretch=1)
        return frame

    def _build_rulebase_section(self) -> QVBoxLayout:
        vbox = QVBoxLayout()
        vbox.setSpacing(6)

        cap = QLabel("RULEBASE")
        cap.setStyleSheet(
            f"color: {C_MUTED}; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;"
        )

        row = QHBoxLayout()
        row.setSpacing(6)
        self.rulebase_status = QLabel(self._rule_cache_text(self.rule_cache))
        self.rulebase_status.setMinimumWidth(180)
        self.rulebase_status.setStyleSheet(
            f"color: {C_TEXT}; font-size: 12px; background: transparent; border: none;"
        )
        manifest_btn = QPushButton("버전 확인")
        manifest_btn.setMinimumWidth(84)
        manifest_btn.clicked.connect(self.check_rule_manifest)

        row.addWidget(self.rulebase_status)
        row.addWidget(manifest_btn)

        vbox.addWidget(cap)
        vbox.addLayout(row)
        return vbox

    def _build_folder_section(self) -> QVBoxLayout:
        vbox = QVBoxLayout()
        vbox.setSpacing(6)
        vbox.setContentsMargins(16, 0, 0, 0)

        cap = QLabel("점검 폴더")
        cap.setStyleSheet(
            f"color: {C_MUTED}; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;"
        )

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.folder_path = QLineEdit()
        self.folder_path.setReadOnly(True)
        self.folder_path.setPlaceholderText("점검 대상 폴더를 선택하세요")
        self.browse_btn = QPushButton("폴더 선택")
        self.browse_btn.setMinimumWidth(88)
        self.browse_btn.clicked.connect(self.choose_folder)
        row1.addWidget(self.folder_path, stretch=1)
        row1.addWidget(self.browse_btn)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        pn_label = _muted("프로젝트 번호")
        self.project_number = QLineEdit()
        self.project_number.setPlaceholderText("TTA-26-00000")
        self.project_number.setFixedWidth(140)
        self.metadata_btn = QPushButton("기준정보 조회")
        self.metadata_btn.setMinimumWidth(104)
        self.metadata_btn.clicked.connect(self.fetch_metadata)
        self.manual_metadata_btn = QPushButton("직접 입력")
        self.manual_metadata_btn.setMinimumWidth(84)
        self.manual_metadata_btn.clicked.connect(self.enter_metadata_manually)
        self.scan_btn = QPushButton("파일 스캔")
        self.scan_btn.setMinimumWidth(88)
        self.scan_btn.clicked.connect(self.scan_files)
        self.run_btn = QPushButton("점검 실행")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setMinimumWidth(116)
        self.run_btn.setFixedHeight(38)
        # 짙은 네이비를 위젯에 직접 지정(전역 QSS 미적용 상황까지 방지).
        self.run_btn.setStyleSheet(
            "QPushButton {"
            " background-color: #0a357f; color: #ffffff;"
            " border: 1px solid #082a66; border-radius: 3px;"
            " font-weight: 800; font-size: 12px; padding: 0 12px; }"
            "QPushButton:hover { background-color: #082a66; }"
            "QPushButton:pressed { background-color: #061f4d; }"
            "QPushButton:disabled { background-color: #aebfd9; color: #eef2fb;"
            " border: 1px solid #93a6c9; }"
        )
        self.run_btn.clicked.connect(self.run_local_review)
        self.action_status = QLabel("대기")
        self.action_status.setMinimumWidth(130)
        self.action_status.setStyleSheet(
            f"color: {C_MUTED}; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        row2.addWidget(pn_label)
        row2.addWidget(self.project_number)
        row2.addWidget(self.metadata_btn)
        row2.addWidget(self.manual_metadata_btn)
        row2.addWidget(self.scan_btn)
        row2.addStretch()
        row2.addWidget(self.action_status)
        row2.addWidget(self.run_btn)

        vbox.addWidget(cap)
        vbox.addLayout(row1)
        vbox.addLayout(row2)
        return vbox

    # ── Body: left sidebar + result panel ────────────────────────────────────

    def _build_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setSizes([320, 940])
        return splitter

    # ── Left panel: metadata + file list ─────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        # 배경 미지정(투명) → 회색 캔버스가 그대로 보이고, 내부 카드(#panel)만 흰색.
        # (bare 흰색을 주면 자식에 전파되어 왼쪽 컬럼만 흰색이 되는 불일치가 생긴다.)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_metadata_card())
        layout.addWidget(self._build_file_card(), stretch=1)
        return w

    def _build_metadata_card(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.addWidget(_section_title("프로젝트 정보"))
        title_row.addStretch()
        gs_search_btn = QPushButton("GS 검색")
        gs_search_btn.setMinimumWidth(76)
        gs_search_btn.setToolTip("GS 인증 이력 DB에서 회사/제품을 검색하여 자동 채우기")
        gs_search_btn.clicked.connect(self.open_reference_search)
        title_row.addWidget(gs_search_btn)
        layout.addLayout(title_row)
        layout.addWidget(_hsep())

        grid = QGridLayout()
        grid.setSpacing(7)
        grid.setColumnMinimumWidth(0, 72)
        grid.setColumnStretch(1, 1)

        fields = [
            ("회사명", "company"),
            ("제품명", "product"),
            ("PL",    "pl"),
            ("WD",    "wd"),
            ("인증일", "cert_date"),
            ("점검결과", "review"),
        ]
        for i, (label_text, attr_name) in enumerate(fields):
            key_lbl = QLabel(label_text)
            key_lbl.setStyleSheet(
                f"color: {C_MUTED}; font-size: 12px; font-weight: 600;"
                " background: transparent; border: none;"
            )
            val_lbl = QLabel("—")
            val_lbl.setWordWrap(True)
            val_lbl.setStyleSheet(
                f"color: {C_TEXT}; font-size: 12px;"
                " background: transparent; border: none;"
            )
            setattr(self, attr_name, val_lbl)
            grid.addWidget(key_lbl, i, 0, Qt.AlignTop)
            grid.addWidget(val_lbl, i, 1, Qt.AlignTop)

        layout.addLayout(grid)
        return frame

    def _build_file_card(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(_section_title("파일 목록"))
        header.addStretch()
        self.file_count_label = _muted("0개")
        header.addWidget(self.file_count_label)
        layout.addLayout(header)

        # 스캔 진행 표시 (busy indicator) — 스캔 중에만 표시
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 0)  # indeterminate
        self.scan_progress.setTextVisible(False)
        self.scan_progress.setVisible(False)
        layout.addWidget(self.scan_progress)

        layout.addWidget(_hsep())

        self.file_table = QTableWidget(0, 3)
        self.file_table.setHorizontalHeaderLabels(["파일명", "확장자", "크기(B)"])
        hdr = self.file_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSortingEnabled(True)
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setAlternatingRowColors(True)
        layout.addWidget(self.file_table, stretch=1)
        return frame

    # ── Result panel ──────────────────────────────────────────────────────────

    def _build_result_panel(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        # Header row: title + stat badges
        header = QHBoxLayout()
        title = _section_title("점검 결과")
        title_font = title.font()
        title_font.setPointSize(13)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()

        self._stat_labels: dict[str, QLabel] = {}
        for key, fg, bg, text in [
            ("total",       C_TEXT,    "#eef2f6",      "전체 0"),
            ("pass",        C_SUCCESS, C_SUCCESS_SOFT, "적합 0"),
            ("fail",        C_DANGER,  C_DANGER_SOFT,  "부적합 0"),
            ("unsupported", C_MUTED,   "#eef2f6",      "미지원 0"),
            ("error",       C_WARNING, C_WARNING_SOFT, "오류 0"),
        ]:
            badge = _stat_badge(text, fg, bg)
            self._stat_labels[key] = badge
            header.addWidget(badge)

        layout.addLayout(header)
        layout.addWidget(_hsep())

        # Result table
        self.result_table = QTableWidget(0, 5)
        self.result_table.setHorizontalHeaderLabels(["결과", "점검항목", "기대값", "실제값", "메시지"])
        hdr = self.result_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.result_table.setColumnWidth(0, 70)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(False)
        self.result_table.verticalHeader().setVisible(False)
        # 하위 검사를 rowspan으로 묶어 표시하므로 헤더 클릭 정렬은 끈다(정렬 시 그룹이 깨짐).
        self.result_table.setSortingEnabled(False)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setWordWrap(True)
        self.result_table.setAlternatingRowColors(True)
        # 행을 더블클릭하면 엔진이 계산한 상세 근거(raw_detail)를 팝업으로 보여준다.
        self.result_table.cellDoubleClicked.connect(self._show_result_detail)
        layout.addWidget(self.result_table, stretch=1)
        return frame

    # ── Business logic ────────────────────────────────────────────────────────

    def check_health(self):
        try:
            payload = self._client().health()
        except ApiClientError as exc:
            self._show_error(str(exc))
            return
        QMessageBox.information(self, "연결 확인", f"서버 연결 정상\n{payload.get('server_time', '')}")

    def check_rule_manifest(self):
        """서버와 로컬 규칙 버전을 확인하고, 다르면 자동으로 동기화(업데이트)한다.

        - 버전이 같으면 조회만 하고 '업데이트가 필요 없습니다.' 안내.
        - 버전이 다르면 서버에서 규칙 번들을 내려받아 동기화 후 '업데이트가 완료 되었습니다.' 안내.
        """
        try:
            manifest = self._client().rule_manifest()
        except ApiClientError as exc:
            self._show_error(str(exc))
            return
        cached = self.rule_cache.rulebase_version or ""
        server = manifest.get("rulebase_version") or ""

        version_lines = [
            f"서버 규칙 버전: {server or '(없음)'}",
            f"로컬 규칙 버전: {cached or '(없음)'}",
            f"규칙 개수: {manifest.get('rule_count', 0)}",
            f"필요 엔진 버전: {manifest.get('engine_min_version', '')}",
        ]

        # 버전이 같으면 업데이트 불필요 → 조회만 한다.
        if cached and server and cached == server:
            QMessageBox.information(
                self,
                "규칙 버전 확인",
                "\n".join([*version_lines, "", "업데이트가 필요 없습니다."]),
            )
            return

        # 버전이 다르면(또는 로컬 규칙 없음) 서버와 동기화한다.
        try:
            bundle = self._client().rule_bundle()
            self.rule_cache = save_rule_cache(bundle)
        except ApiClientError as exc:
            self._show_error(str(exc))
            return
        except OSError as exc:
            self._show_error(f"규칙 캐시 저장에 실패했습니다: {exc}")
            return
        self.rulebase_status.setText(self._rule_cache_text(self.rule_cache))
        required_engine = str(bundle.get("engine_min_version") or "")
        if not engine_supports(required_engine):
            QMessageBox.warning(
                self,
                "앱 업데이트 필요",
                f"규칙을 내려받았지만, 이 규칙셋은 엔진 v{required_engine} 이상이 필요합니다.\n"
                f"현재 앱 엔진은 v{ENGINE_VERSION} 이라 점검이 차단됩니다.\n"
                "최신 GSCertLocalReview 로 업데이트(재설치)하세요.",
            )
            return
        QMessageBox.information(
            self,
            "규칙 버전 확인",
            "\n".join([
                f"서버 규칙 버전: {server or '(없음)'}",
                f"로컬 규칙 버전: {self.rule_cache.rulebase_version}",
                f"규칙 수: {self.rule_cache.rule_count}",
                "",
                "업데이트가 완료 되었습니다.",
            ]),
        )

    def choose_folder(self):
        folder_name = QFileDialog.getExistingDirectory(self, "점검 대상 폴더 선택")
        if not folder_name:
            return
        folder = Path(folder_name)
        self.selected_folder = folder
        self.folder_path.setText(str(folder))
        self._save_settings()
        inferred = infer_project_number(folder)
        if inferred and not self.project_number.text().strip():
            self.project_number.setText(inferred)
        # 폴더 선택 시 파일 스캔을 먼저 하고, 스캔 완료 후 기준정보 조회를 자동 실행한다.
        # (스캔이 끝나야 조회 실패 시 합의서에서 회사/제품명을 추출해 채울 수 있다.)
        self._auto_fetch_after_scan = bool(self.project_number.text().strip())
        self.scan_files()

    def fetch_metadata(self):
        project_number = self.project_number.text().strip()
        if not project_number:
            self._show_error("프로젝트 번호를 입력하거나 프로젝트 번호가 포함된 폴더를 선택하세요.")
            return
        try:
            # 센터 미지정 → 서버가 전체 센터에서 프로젝트번호로 조회한다.
            metadata = self._client().project_metadata(project_number)
        except ApiClientError as exc:
            # 오프라인/서버 오류: 점검은 메타데이터가 필수이므로 직접 입력을 제안한다.
            answer = QMessageBox.question(
                self,
                "기준정보 조회 실패",
                f"서버에서 기준정보를 가져오지 못했습니다.\n{exc}\n\n직접 입력하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.enter_metadata_manually()
            return
        self._set_metadata(metadata)

    def enter_metadata_manually(self):
        project_number = self.project_number.text().strip()
        prefill = self._agreement_prefill()
        dialog = ManualMetadataDialog(
            project_number, initial=self.current_metadata, prefill=prefill, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_metadata is not None:
            self._set_metadata(dialog.result_metadata)
            self._set_action_status("기준정보 입력됨", C_SUCCESS)

    def _agreement_prefill(self) -> dict:
        """파일 스캔이 완료된 경우, '합의서' Word(.docx) 파일에서 회사명/제품명을 추출해
        직접 입력 창의 초기값으로 제공한다(구글시트 자동 조회 실패 시 보조)."""
        scan = self.scan
        if scan is None:
            return {}
        agreement = next(
            (
                f for f in scan.files
                if "합의서" in f.name and f.extension in (".docx", ".docm", ".doc")
            ),
            None,
        )
        if agreement is None:
            return {}
        try:
            from .agreement_parser import extract_agreement_names

            company, product = extract_agreement_names(scan.folder / agreement.relative_path)
        except Exception:
            return {}
        prefill: dict = {}
        if company:
            prefill["company_name"] = company
        if product:
            prefill["product_name"] = product
        return prefill

    def scan_files(self):
        if self._scan_worker is not None:
            self._set_action_status("스캔 진행 중", C_PRIMARY)
            return  # 이미 스캔 진행 중
        folder_text = self.folder_path.text().strip()
        if not folder_text:
            self._set_action_status("폴더 선택 필요", C_WARNING)
            self._show_error("먼저 점검 대상 폴더를 선택하세요.")
            return
        folder = Path(folder_text)
        if not folder.is_dir():
            self._set_action_status("폴더 확인 실패", C_DANGER)
            self._show_error("선택한 폴더가 존재하지 않습니다.")
            return

        self._set_scanning(True)
        self._set_action_status("파일 스캔 중", C_PRIMARY)
        self.file_table.setRowCount(0)
        self.file_count_label.setText("스캔 중… 0개")

        worker = ScanWorker(folder, parent=self)
        worker.progress.connect(self._on_scan_progress)
        worker.done.connect(self._on_scan_done)
        worker.failed.connect(self._on_scan_failed)
        worker.finished.connect(self._on_scan_thread_finished)
        self._scan_worker = worker
        worker.start()

    def _on_scan_progress(self, count: int):
        self.file_count_label.setText(f"스캔 중… {count:,}개")

    def _on_scan_done(self, scan: FolderScan):
        self.scan = scan
        self._set_file_rows(scan)
        self._set_action_status("점검 실행 가능", C_SUCCESS)
        # 폴더 선택으로 시작된 스캔이면, 스캔 완료 후 기준정보 조회를 자동 실행한다.
        if getattr(self, "_auto_fetch_after_scan", False):
            self._auto_fetch_after_scan = False
            if self.project_number.text().strip():
                self.fetch_metadata()

    def _on_scan_failed(self, message: str):
        self.scan = None
        self.file_count_label.setText("0개")
        self._set_action_status("스캔 실패", C_DANGER)
        self._show_error(f"폴더 스캔 중 오류가 발생했습니다:\n{message}")

    def _on_scan_thread_finished(self):
        self._scan_worker = None
        self._set_scanning(False)

    def _set_scanning(self, scanning: bool):
        self.scan_progress.setVisible(scanning)
        self.browse_btn.setEnabled(not scanning)
        self.scan_btn.setEnabled(not scanning)
        self.run_btn.setEnabled(not scanning)
        self.scan_btn.setText("스캔 중…" if scanning else "파일 스캔")

    def run_local_review(self):
        if self._scan_worker is not None or self._review_worker is not None:
            self._set_action_status("다른 작업 진행 중", C_WARNING)
            self._show_error("현재 다른 작업이 진행 중입니다.")
            return
        if self.scan is None:
            self._set_action_status("파일 스캔 필요", C_WARNING)
            self._show_error("먼저 파일 스캔을 실행하세요.")
            return
        rule_bundle = load_rule_bundle()
        if not rule_bundle:
            self._set_action_status("규칙 업데이트 필요", C_WARNING)
            self._show_error("먼저 Rulebase에서 '버전 확인'을 눌러 규칙을 내려받으세요.")
            return
        # 규칙셋이 요구하는 엔진 버전보다 이 앱의 엔진이 낡았으면 오작동하므로 막는다.
        required_engine = str(rule_bundle.get("engine_min_version") or "")
        if not engine_supports(required_engine):
            self._set_action_status("앱 업데이트 필요", C_WARNING)
            self._show_error(
                f"이 규칙셋은 엔진 v{required_engine} 이상이 필요하지만, "
                f"현재 앱 엔진은 v{ENGINE_VERSION} 입니다.\n"
                "최신 GSCertLocalReview 로 업데이트(재설치)한 뒤 다시 시도하세요."
            )
            return
        # 기준정보(메타데이터)는 점검에 필수다. 시험기간 등 컨텍스트가 없으면 규칙이
        # 조용히 부적합으로 떨어지므로, 없으면 점검을 막고 조회/직접입력을 유도한다.
        if not self._has_metadata():
            self._set_action_status("기준정보 필요", C_WARNING)
            self._show_error(
                "점검에는 기준정보가 필요합니다.\n'기준정보 조회'(온라인) 또는 '직접 입력'(오프라인)으로 "
                "회사/제품/시험 시작·종료일 등을 먼저 채우세요."
            )
            return

        self._set_reviewing(True)
        self._review_worker = ReviewWorker(
            self.scan,
            rule_bundle,
            self.project_number.text().strip(),
            self.current_metadata,
            parent=self,
        )
        self._review_worker.done.connect(self._on_review_thread_done)
        self._review_worker.failed.connect(self._on_review_thread_failed)
        self._review_worker.finished.connect(self._on_review_thread_finished)
        self._review_worker.start()

    def _set_reviewing(self, reviewing: bool):
        self.browse_btn.setEnabled(not reviewing)
        self.metadata_btn.setEnabled(not reviewing)
        self.scan_btn.setEnabled(not reviewing)
        self.project_number.setEnabled(not reviewing)
        self.run_btn.setEnabled(not reviewing)
        self.run_btn.setText("점검 중…" if reviewing else "점검 실행")
        if reviewing:
            self._set_action_status("점검 실행 중", C_PRIMARY)
            self.scan_progress.setVisible(True)
            self.result_table.setRowCount(0)
        else:
            self.scan_progress.setVisible(False)

    def _on_review_thread_done(self, summary):
        self._review_worker = None
        self._set_reviewing(False)
        self._set_result_rows(summary)
        self._set_action_status("점검 완료", C_SUCCESS)

    def _on_review_thread_failed(self, message: str):
        self._review_worker = None
        self._set_reviewing(False)
        self._set_action_status("점검 오류", C_DANGER)
        self._show_error(f"점검 중 오류가 발생했습니다:\n{message}")

    def _on_review_thread_finished(self):
        # done/failed 시그널 없이 스레드가 종료된 경우 UI 잠금 해제
        if self._review_worker is not None:
            self._review_worker = None
            self._set_reviewing(False)
            self._set_action_status("점검 중단", C_DANGER)
            self._show_error("점검 스레드가 예기치 않게 종료되었습니다.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def open_reference_search(self):
        dialog = ReferenceSearchDialog(self._client(), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected:
            item = dialog.selected
            self.current_metadata = ProjectMetadata(
                project_number=self.project_number.text().strip(),
                company_name=item.company,
                product_name=item.product,
                cert_date=item.cert_date,
                start_date=item.start_date,
                end_date=item.end_date,
            )
            self.company.setText(item.company or "—")
            self.product.setText(item.product or "—")
            self.cert_date.setText(item.cert_date or "—")
            self.review.setText("—")
            self.review.setStyleSheet(
                f"color: {C_TEXT}; font-size: 12px;"
                " background: transparent; border: none;"
            )

    def _client(self) -> GSCertApiClient:
        return GSCertApiClient(
            self.server_url.text().strip() or DEFAULT_SERVER_URL,
            token=self.api_token.text().strip(),
        )

    def _has_metadata(self) -> bool:
        """점검에 필요한 최소 기준정보가 채워졌는지. 컨텍스트 의존 규칙(날짜 등)을 위해
        최소한 시험 시작/종료일이 있어야 한다."""
        m = self.current_metadata
        if m is None:
            return False
        return bool((m.start_date or "").strip() and (m.end_date or "").strip())

    def _show_result_detail(self, row: int, _col: int):
        # rowspan 으로 일부 열이 비어 있을 수 있으므로, 행의 어느 셀이든 데이터를 찾는다.
        result = None
        for col in range(self.result_table.columnCount()):
            cell = self.result_table.item(row, col)
            if cell is not None:
                data = cell.data(Qt.ItemDataRole.UserRole)
                if data is not None:
                    result = data
                    break
        if result is None:
            return
        lines = [
            f"점검항목: {result.rule_name}",
            f"규칙코드: {result.rule_code}",
            f"결과: {result.status}",
            f"기대값: {result.expected}",
            f"실제값: {result.actual}",
            f"메시지: {result.message}",
        ]
        if result.file_path:
            lines.append(f"대상: {result.file_path}")
        detail_text = "\n".join(lines)
        raw = getattr(result, "raw_detail", None)
        if raw:
            try:
                detail_text += "\n\n[상세 근거]\n" + json.dumps(raw, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                detail_text += "\n\n[상세 근거]\n" + str(raw)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"점검 상세 — {result.rule_name}")
        dialog.setMinimumSize(560, 420)
        vbox = QVBoxLayout(dialog)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(detail_text)
        vbox.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        vbox.addWidget(buttons)
        dialog.exec()

    def _rule_cache_text(self, summary: RuleCacheSummary) -> str:
        if not summary.exists:
            return "로컬 규칙 없음"
        return f"v{summary.rulebase_version} · {summary.rule_count}개 규칙"

    def _set_metadata(self, metadata: ProjectMetadata):
        self.current_metadata = metadata
        self.company.setText(metadata.company_name or "—")
        self.product.setText(metadata.product_name or "—")
        self.pl.setText(metadata.pl_name or "—")
        self.wd.setText(metadata.wd_name or "—")
        self.cert_date.setText(metadata.cert_date or "—")
        review_text = metadata.review or "—"
        color = REVIEW_COLOR.get(review_text, C_TEXT)
        self.review.setText(review_text)
        self.review.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;"
        )

    def _set_file_rows(self, scan: FolderScan):
        self.file_table.setSortingEnabled(False)
        self.file_table.setRowCount(len(scan.files))
        self.file_count_label.setText(f"{scan.file_count}개 · {scan.total_size_mb} MB")
        for row, file in enumerate(scan.files):
            for col, value in enumerate([file.name, file.extension, str(file.size_bytes)]):
                item = QTableWidgetItem(value)
                if col == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.file_table.setItem(row, col, item)
        self.file_table.setSortingEnabled(True)

    @staticmethod
    def _split_slash(value) -> list[str]:
        """" / " 로 이어진 문자열을 하위 검사 단위로 분해한다(웹과 동일)."""
        if value is None or value == "":
            return []
        return [part.strip() for part in str(value).split(" / ")]

    def _sub_checks(self, result: "LocalRuleResult") -> list[tuple[str, str, bool | None, str]]:
        """규칙 결과를 하위 검사 [(기대값, 실제값, 통과여부, 메시지)] 로 분해한다(웹 ruleSubChecks 동일).

        - raw_detail.sub_checks 가 있으면 그대로 사용(각 항목별 통과여부/메시지 포함).
        - 없으면 기대값/실제값을 " / " 로 분해. file_checks/content_checks 개수가 맞으면
          행별 통과여부를 부여한다.
        - 1건 이하이면 빈 리스트를 반환해 호출부가 단일 행으로 처리하게 한다.
        """
        rd = result.raw_detail or {}
        subs = rd.get("sub_checks")
        if isinstance(subs, list) and subs:
            out = []
            for sub in subs:
                exp = sub.get("expected")
                act = sub.get("actual")
                passed = sub.get("passed")
                msg = sub.get("message")
                out.append((
                    str(exp) if exp not in (None, "") else "-",
                    str(act) if act not in (None, "") else "-",
                    passed if isinstance(passed, bool) else None,
                    str(msg) if msg not in (None, "") else "",
                ))
            return out

        exp_parts = self._split_slash(result.expected)
        act_parts = self._split_slash(result.actual)
        row_count = max(len(exp_parts), len(act_parts))
        if row_count <= 1:
            return []

        file_checks = rd.get("file_checks") if isinstance(rd.get("file_checks"), list) else []
        content_checks = rd.get("content_checks") if isinstance(rd.get("content_checks"), list) else []
        merged = [*file_checks, *content_checks]
        flags = [c.get("passed") for c in merged]
        use_per_row = len(flags) == row_count and all(isinstance(f, bool) for f in flags)

        rows = []
        for i in range(row_count):
            msg = ""
            if use_per_row and i < len(merged) and isinstance(merged[i], dict):
                msg = str(merged[i].get("message") or "")
            rows.append((
                exp_parts[i] if i < len(exp_parts) else "-",
                act_parts[i] if i < len(act_parts) else "-",
                flags[i] if use_per_row else None,
                msg,
            ))
        return rows

    def _put_status_cell(self, row, col, label, fg, bg, result, tooltip, span=1):
        item = QTableWidgetItem(label)
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignTop if span > 1 else Qt.AlignCenter)
        item.setForeground(QColor(fg))
        item.setBackground(QColor(bg))
        item.setData(Qt.ItemDataRole.UserRole, result)  # 더블클릭 상세용
        item.setToolTip(tooltip or label)
        self.result_table.setItem(row, col, item)
        if span > 1:
            self.result_table.setSpan(row, col, span, 1)

    def _put_text_cell(self, row, col, value, result, span=1, bg=None):
        text = value if value not in (None, "") else "-"
        item = QTableWidgetItem(text)
        if span > 1:
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
        item.setToolTip(text)
        item.setData(Qt.ItemDataRole.UserRole, result)
        if bg is not None:
            item.setBackground(QColor(bg))
        self.result_table.setItem(row, col, item)
        if span > 1:
            self.result_table.setSpan(row, col, span, 1)

    def _set_result_rows(self, summary: LocalRunSummary):
        table = self.result_table
        table.setSortingEnabled(False)
        table.clearContents()
        table.clearSpans()

        # 규칙별로 하위 검사를 분해해 행으로 펼친다(웹과 동일하게 세부 항목까지 표시).
        plan = []
        total_rows = 0
        for result in summary.results:
            subs = self._sub_checks(result)
            plan.append((result, subs))
            total_rows += max(1, len(subs))
        table.setRowCount(total_rows)

        counts = {PASS: 0, FAIL: 0, UNSUPPORTED: 0, ERROR: 0}
        row = 0
        for result, subs in plan:
            counts[result.status] = counts.get(result.status, 0) + 1
            fg, bg, label = STATUS_META.get(result.status, (C_TEXT, C_SOFT, result.status))

            if len(subs) <= 1:
                self._put_status_cell(row, 0, label, fg, bg, result, result.message or label)
                self._put_text_cell(row, 1, result.rule_name, result)
                self._put_text_cell(row, 2, result.expected, result)
                self._put_text_cell(row, 3, result.actual, result)
                self._put_text_cell(row, 4, result.message, result)
                row += 1
                continue

            n = len(subs)
            per_row = subs[0][2] is not None
            # 점검항목은 규칙 단위이므로 rowspan 으로 묶는다.
            self._put_text_cell(row, 1, result.rule_name, result, span=n)
            if not per_row:
                # 하위 통과여부가 없으면 결과/메시지 열도 규칙 전체 하나로 묶는다.
                self._put_status_cell(row, 0, label, fg, bg, result, result.message or label, span=n)
                self._put_text_cell(row, 4, result.message, result, span=n)
            for i, (exp, act, passed, sub_msg) in enumerate(subs):
                r = row + i
                # 부적합 세부 항목은 밝은 회색 배경으로 강조한다.
                row_bg = C_FAIL_ROW if (per_row and not passed) else None
                if per_row:
                    if passed:
                        self._put_status_cell(r, 0, "정상", C_SUCCESS, C_SUCCESS_SOFT, result, exp)
                    else:
                        self._put_status_cell(r, 0, "부적합", C_DANGER, C_FAIL_ROW, result, sub_msg or exp)
                self._put_text_cell(r, 2, exp, result, bg=row_bg)
                self._put_text_cell(r, 3, act, result, bg=row_bg)
                if per_row:
                    # 세부 항목마다 메시지를 생성한다(적합이면 message가 비어 '-' 표시).
                    self._put_text_cell(r, 4, sub_msg, result, bg=row_bg)
            row += n

        self._stat_labels["total"].setText(f"전체 {len(summary.results)}")
        self._stat_labels["pass"].setText(f"적합 {counts.get(PASS, 0)}")
        self._stat_labels["fail"].setText(f"부적합 {counts.get(FAIL, 0)}")
        self._stat_labels["unsupported"].setText(f"미지원 {counts.get(UNSUPPORTED, 0)}")
        self._stat_labels["error"].setText(f"오류 {counts.get(ERROR, 0)}")

        table.resizeRowsToContents()

    def _set_action_status(self, text: str, color: str = C_MUTED):
        self.action_status.setText(text)
        self.action_status.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        # 하단 상태바에도 현재 동작 상태를 미러링한다.
        if hasattr(self, "_status_perm"):
            self.statusBar().showMessage(text)
            self._refresh_status_perm()

    def _show_error(self, message: str):
        QMessageBox.warning(self, "GSCert Local Review", message)

    def _show_help(self):
        """상단 '도움말' 버튼: 간단한 사용법을 안내한다."""
        box = QMessageBox(self)
        box.setWindowTitle("도움말 — 사용법")
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText("<b>GSCert Local Review 사용법</b>")
        box.setInformativeText(
            "<ol style='margin-left:-18px; line-height:1.6;'>"
            "<li><b>서버 연결 확인</b><BR>
            — 상단에 서버 URL을 입력하고 <b>연결 확인</b>을 누릅니다.</li>"
            "<li><b>점검 규칙 확인</b><BR>
            — <b>버전 확인</b>으로 서버와 규칙 버전을 비교합니다.<BR>
            버전이 다르면 자동으로 최신 규칙을 내려받아 동기화합니다.</li>"
            "<li><b>점검 폴더 선택</b><BR>
            — <b>폴더 선택</b>으로 점검할 프로젝트 폴더를 지정합니다.<BR>
            폴더를 지정하면 자동으로 파일들을 스캔 후 프로젝트 정보를 조회합니다.</li>"
            "<li><b>프로젝트 정보 조회</b><BR>
            — <b>기준정보 조회</b>로 프로젝트 정보를 수동 조회 요청할 수 있습니다
            인증위가 완료되지 않은 경우, <b>직접 입력</b>으로 수동 입력해야 합니다."
            "<li><b>파일 스캔</b><BR>
            — <b>파일 스캔</b>으로 폴더 안 파일 목록을 확인합니다.</li>"
            "<li><b>점검 실행</b><BR>
            — <b>점검 실행</b>을 누르면 규칙 검사가 수행되고, <b>점검 결과</b> 표에 적합/부적합/미지원/오류가 표시됩니다.</li>"
            "</ol>"
            "<p style='color:#6b7683;'>점검은 인터넷 없이 로컬에서 수행되며, 규칙은 서버"
            " PostgreSQL에서 관리됩니다.</p>"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()


def main() -> int:
    app = QApplication([])
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    return app.exec()
