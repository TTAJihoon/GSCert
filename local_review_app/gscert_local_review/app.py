from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiClientError, GSCertApiClient, ProjectMetadata, ReferenceItem
from .local_runner import ERROR, FAIL, PASS, UNSUPPORTED, LocalRunSummary, run_cached_rules
from .project import infer_project_number
from .rule_cache import RuleCacheSummary, load_rule_bundle, load_rule_cache, save_rule_cache
from .scanner import FolderScan, scan_folder


DEFAULT_SERVER_URL = "http://127.0.0.1:8000"

# ── Design tokens (ecm_download_review.css 기준) ─────────────────────────────
C_BG           = "#ffffff"
C_SURFACE      = "#ffffff"
C_SOFT         = "#f8fafc"
C_LINE         = "#d7dde5"
C_LINE_STRONG  = "#aeb8c5"
C_TEXT         = "#1f2937"
C_MUTED        = "#667085"
C_PRIMARY      = "#2563eb"
C_PRIMARY_SOFT = "#e8f0ff"
C_SUCCESS      = "#067647"
C_SUCCESS_SOFT = "#e7f6ee"
C_WARNING      = "#b54708"
C_WARNING_SOFT = "#fff4e5"
C_DANGER       = "#b42318"
C_DANGER_SOFT  = "#fdecec"

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
    background-color: {C_BG};
}}
QWidget {{
    font-family: "Malgun Gothic", "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: {C_TEXT};
}}

/* ── Scrollbars ────────────────────────────── */
QScrollBar:vertical {{
    width: 7px;
    background: transparent;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C_LINE_STRONG};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    height: 7px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: {C_LINE_STRONG};
    border-radius: 3px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Panel cards ───────────────────────────── */
QFrame#panel {{
    background-color: {C_SURFACE};
    border: 1px solid {C_LINE};
    border-radius: 8px;
}}

/* ── Inputs ────────────────────────────────── */
QLineEdit, QComboBox {{
    min-height: 34px;
    padding: 0 10px;
    border: 1px solid {C_LINE};
    border-radius: 6px;
    background-color: {C_SURFACE};
    color: {C_TEXT};
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {C_PRIMARY};
}}
QLineEdit:read-only {{
    background-color: {C_SOFT};
    color: {C_MUTED};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {C_LINE};
    border-radius: 6px;
    background: {C_SURFACE};
    selection-background-color: {C_PRIMARY_SOFT};
    selection-color: {C_TEXT};
    outline: none;
}}

/* ── Buttons ───────────────────────────────── */
QPushButton {{
    min-height: 34px;
    padding: 0 14px;
    border: 1px solid {C_LINE};
    border-radius: 6px;
    background-color: {C_SURFACE};
    color: {C_TEXT};
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {C_SOFT};
    border-color: {C_LINE_STRONG};
}}
QPushButton:pressed {{
    background-color: #edf0f4;
}}
QPushButton:disabled {{
    color: #98a2b3;
    background-color: #eef2f6;
    border-color: {C_LINE_STRONG};
}}
QPushButton#primaryBtn {{
    background-color: #0f4fd6;
    color: #ffffff;
    border: 1px solid #0b3fb0;
    font-weight: 800;
}}
QPushButton#primaryBtn:hover {{
    background-color: #0b46c6;
    color: #ffffff;
    border: 1px solid #0b3fb0;
}}
QPushButton#primaryBtn:pressed {{
    background-color: #08358f;
    color: #ffffff;
    border: 1px solid #08358f;
}}
QPushButton#primaryBtn:disabled {{
    background-color: #dbeafe;
    color: #1e3a8a;
    border: 1px solid #93c5fd;
}}

/* ── Tables ────────────────────────────────── */
QTableWidget {{
    background-color: {C_SURFACE};
    border: 1px solid {C_LINE};
    border-radius: 8px;
    gridline-color: #edf0f4;
    selection-background-color: {C_PRIMARY_SOFT};
    selection-color: {C_TEXT};
    outline: none;
}}
QTableWidget::item {{
    padding: 7px 10px;
    border-bottom: 1px solid #edf0f4;
}}
QTableWidget::item:selected {{
    background-color: {C_PRIMARY_SOFT};
    color: {C_TEXT};
}}
QTableWidget[alternatingRowColors="true"]::item:alternate {{
    background-color: {C_SOFT};
}}
QHeaderView::section {{
    background-color: {C_SOFT};
    color: #475467;
    font-weight: 700;
    font-size: 12px;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {C_LINE};
    border-right: 1px solid {C_LINE};
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── Progress bar (busy indicator) ─────────── */
QProgressBar {{
    border: 1px solid {C_LINE};
    border-radius: 5px;
    background-color: {C_SOFT};
    max-height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {C_PRIMARY};
    border-radius: 4px;
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

        root = QWidget()
        root.setStyleSheet(f"background-color: {C_BG};")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_controls())
        outer.addWidget(self._build_body(), stretch=1)

        self.setCentralWidget(root)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QFrame:
        frame = _panel()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 13, 18, 13)
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

        center_col = QVBoxLayout()
        center_col.setSpacing(3)
        center_col.addWidget(_muted("센터"))
        self.center = QComboBox()
        self.center.addItem("상암", "sangam")
        self.center.addItem("영남", "yeongnam")
        self.center.setFixedWidth(86)
        center_col.addWidget(self.center)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(3)
        btn_col.addWidget(QLabel(" "))  # spacer to align with labels above
        health_btn = QPushButton("연결 확인")
        health_btn.setMinimumWidth(92)
        health_btn.clicked.connect(self.check_health)
        btn_col.addWidget(health_btn)

        right.addLayout(url_col)
        right.addLayout(center_col)
        right.addLayout(btn_col)

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
        update_btn = QPushButton("규칙 업데이트")
        update_btn.setMinimumWidth(108)
        update_btn.clicked.connect(self.update_rules)

        row.addWidget(self.rulebase_status)
        row.addWidget(manifest_btn)
        row.addWidget(update_btn)

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
        self.scan_btn = QPushButton("파일 스캔")
        self.scan_btn.setMinimumWidth(88)
        self.scan_btn.clicked.connect(self.scan_files)
        self.run_btn = QPushButton("점검 실행")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setMinimumWidth(116)
        self.run_btn.setFixedHeight(38)
        self.run_btn.setStyleSheet(f"""
            QPushButton#primaryBtn {{
                background-color: #0f4fd6;
                color: #ffffff;
                border: 1px solid #0b3fb0;
                border-radius: 6px;
                font-weight: 800;
                font-size: 13px;
                min-height: 38px;
                padding: 0 16px;
            }}
            QPushButton#primaryBtn:hover {{
                background-color: #0b46c6;
                color: #ffffff;
                border-color: #0b3fb0;
            }}
            QPushButton#primaryBtn:pressed {{
                background-color: #08358f;
                color: #ffffff;
                border-color: #08358f;
            }}
            QPushButton#primaryBtn:disabled {{
                background-color: #dbeafe;
                color: #1e3a8a;
                border-color: #93c5fd;
            }}
        """)
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
        w.setStyleSheet(f"background-color: {C_BG};")
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
        self.result_table.setSortingEnabled(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setWordWrap(True)
        self.result_table.setAlternatingRowColors(True)
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
        try:
            manifest = self._client().rule_manifest()
        except ApiClientError as exc:
            self._show_error(str(exc))
            return
        cached = self.rule_cache.rulebase_version or "(없음)"
        server = manifest.get("rulebase_version") or "(없음)"
        QMessageBox.information(
            self,
            "규칙 버전 확인",
            "\n".join([
                f"서버 규칙 버전: {server}",
                f"로컬 규칙 버전: {cached}",
                f"규칙 개수: {manifest.get('rule_count', 0)}",
                f"필요 엔진 버전: {manifest.get('engine_min_version', '')}",
            ]),
        )

    def update_rules(self):
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
        QMessageBox.information(
            self,
            "규칙 업데이트",
            f"규칙을 업데이트했습니다.\n버전: {self.rule_cache.rulebase_version}\n규칙 수: {self.rule_cache.rule_count}",
        )

    def choose_folder(self):
        folder_name = QFileDialog.getExistingDirectory(self, "점검 대상 폴더 선택")
        if not folder_name:
            return
        folder = Path(folder_name)
        self.selected_folder = folder
        self.folder_path.setText(str(folder))
        inferred = infer_project_number(folder)
        if inferred and not self.project_number.text().strip():
            self.project_number.setText(inferred)
        self.scan_files()

    def fetch_metadata(self):
        project_number = self.project_number.text().strip()
        if not project_number:
            self._show_error("프로젝트 번호를 입력하거나 프로젝트 번호가 포함된 폴더를 선택하세요.")
            return
        try:
            metadata = self._client().project_metadata(project_number, self.center.currentData())
        except ApiClientError as exc:
            self._show_error(str(exc))
            return
        self._set_metadata(metadata)

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
            self._show_error("먼저 Rulebase에서 규칙 업데이트를 실행하세요.")
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
        return GSCertApiClient(self.server_url.text().strip() or DEFAULT_SERVER_URL)

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

    def _set_result_rows(self, summary: LocalRunSummary):
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(len(summary.results))

        counts = {PASS: 0, FAIL: 0, UNSUPPORTED: 0, ERROR: 0}
        for row, result in enumerate(summary.results):
            counts[result.status] = counts.get(result.status, 0) + 1
            fg, bg, label = STATUS_META.get(result.status, (C_TEXT, C_SOFT, result.status))

            status_item = QTableWidgetItem(label)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(fg))
            status_item.setBackground(QColor(bg))
            self.result_table.setItem(row, 0, status_item)

            for col, value in enumerate(
                [result.rule_name, result.expected, result.actual, result.message],
                start=1,
            ):
                self.result_table.setItem(row, col, QTableWidgetItem(value))

        self._stat_labels["total"].setText(f"전체 {len(summary.results)}")
        self._stat_labels["pass"].setText(f"적합 {counts.get(PASS, 0)}")
        self._stat_labels["fail"].setText(f"부적합 {counts.get(FAIL, 0)}")
        self._stat_labels["unsupported"].setText(f"미지원 {counts.get(UNSUPPORTED, 0)}")
        self._stat_labels["error"].setText(f"오류 {counts.get(ERROR, 0)}")

        self.result_table.resizeRowsToContents()
        self.result_table.setSortingEnabled(True)

    def _set_action_status(self, text: str, color: str = C_MUTED):
        self.action_status.setText(text)
        self.action_status.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;"
        )

    def _show_error(self, message: str):
        QMessageBox.warning(self, "GSCert Local Review", message)


def main() -> int:
    app = QApplication([])
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    return app.exec()
