from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gscert_review_core.result_display import DisplayResultRow, build_display_rows

from .app import (
    APP_QSS,
    C_BG,
    C_DANGER,
    C_DANGER_SOFT,
    C_LINE,
    C_MUTED,
    C_PRIMARY,
    C_PRIMARY_SOFT,
    C_RESULT_SELECT,
    C_SOFT,
    C_SUCCESS,
    C_SUCCESS_SOFT,
    C_SURFACE,
    C_TEXT,
    C_WARNING,
    C_WARNING_SOFT,
    DEFAULT_SERVER_URL,
    ERROR,
    FAIL,
    MainWindow,
    PASS,
    STATUS_META,
    UNSUPPORTED,
    _hsep,
    _muted,
    _panel,
    _section_title,
)


def _label_style(color: str = C_TEXT, size: int = 12, weight: int = 400) -> str:
    return (
        f"color: {color}; font-size: {size}px; font-weight: {weight};"
        " background: transparent; border: none;"
    )


def _value_label(text: str = "-") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(_label_style(C_TEXT, 12, 500))
    return label


def _soft_card() -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background-color: #fbfdff; border: 1px solid {C_LINE};"
        " border-radius: 8px; }}"
        "QLabel { background: transparent; border: none; }"
    )
    return frame


class DashboardWindow(MainWindow):
    """3B layout variant.

    The original app remains available via ``gscert_local_review.app.MainWindow``.
    This class reuses its business logic and replaces only the shell layout.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GSCert Local Review Dashboard")

    def _build_controls(self) -> QWidget:
        controls = QWidget()
        controls.setFixedHeight(0)
        controls.setVisible(False)
        return controls

    def _build_header(self) -> QFrame:
        frame = _panel()
        frame.setObjectName("headerBar")
        frame.setStyleSheet(
            f"QFrame#headerBar {{ background-color: {C_SURFACE};"
            f" border: 1px solid {C_LINE}; border-radius: 8px; }}"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        eyebrow = QLabel("GSCert · ECM 제출물 점검 도구")
        eyebrow.setStyleSheet(_label_style(C_MUTED, 11, 700))
        title = QLabel("GSCert Local Review")
        title.setStyleSheet(_label_style(C_TEXT, 20, 800))
        title_col.addWidget(eyebrow)
        title_col.addWidget(title)

        layout.addLayout(title_col)
        layout.addStretch()

        server_col = QVBoxLayout()
        server_col.setSpacing(3)
        server_col.addWidget(_muted("서버 URL"))
        self.server_url = QLineEdit(DEFAULT_SERVER_URL)
        self.server_url.setMinimumWidth(230)
        server_col.addWidget(self.server_url)

        token_col = QVBoxLayout()
        token_col.setSpacing(3)
        token_col.addWidget(_muted("API 토큰(선택)"))
        self.api_token = QLineEdit()
        self.api_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_token.setPlaceholderText("서버가 요구할 때만")
        self.api_token.setFixedWidth(150)
        token_col.addWidget(self.api_token)

        layout.addLayout(server_col)
        layout.addLayout(token_col)

        health_btn = QPushButton("연결 확인")
        health_btn.setMinimumWidth(92)
        health_btn.clicked.connect(self.check_health)
        layout.addWidget(health_btn, alignment=Qt.AlignBottom)

        help_btn = QPushButton("도움말")
        help_btn.setMinimumWidth(74)
        help_btn.clicked.connect(self._show_help)
        layout.addWidget(help_btn, alignment=Qt.AlignBottom)

        self.run_btn = QPushButton("점검 실행")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setMinimumWidth(118)
        self.run_btn.setFixedHeight(38)
        self.run_btn.clicked.connect(self.run_local_review)
        layout.addWidget(self.run_btn, alignment=Qt.AlignBottom)
        return frame

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        setup_panel = self._build_setup_panel()
        setup_panel.setFixedWidth(320)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(14)
        workspace_layout.addWidget(self._build_summary_row())

        lower = QWidget()
        lower_layout = QHBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(14)
        lower_layout.addWidget(self._build_result_panel(), stretch=3)
        lower_layout.addWidget(self._build_detail_panel(), stretch=2)
        workspace_layout.addWidget(lower, stretch=1)

        layout.addWidget(setup_panel)
        layout.addWidget(workspace, stretch=1)
        return body

    def _build_setup_panel(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        layout.addWidget(_section_title("준비 정보"))

        folder_title = QLabel("폴더 설정")
        folder_title.setStyleSheet(_label_style(C_TEXT, 13, 700))
        layout.addWidget(folder_title)

        self.folder_path = QLineEdit()
        self.folder_path.setReadOnly(True)
        self.folder_path.setPlaceholderText("점검 대상 폴더를 선택하세요")
        layout.addWidget(self.folder_path)

        folder_buttons = QHBoxLayout()
        folder_buttons.setSpacing(8)
        self.browse_btn = QPushButton("폴더 선택")
        self.browse_btn.clicked.connect(self.choose_folder)
        self.scan_btn = QPushButton("파일 스캔")
        self.scan_btn.clicked.connect(self.scan_files)
        folder_buttons.addWidget(self.browse_btn)
        folder_buttons.addWidget(self.scan_btn)
        layout.addLayout(folder_buttons)

        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 0)
        self.scan_progress.setTextVisible(False)
        self.scan_progress.setVisible(False)
        layout.addWidget(self.scan_progress)

        self.file_count_label = _muted("파일 0개")
        layout.addWidget(self.file_count_label)
        layout.addWidget(_hsep())

        gs_title = QLabel("GS 프로젝트 정보")
        gs_title.setStyleSheet(_label_style(C_TEXT, 13, 700))
        layout.addWidget(gs_title)

        self.project_number = QLineEdit()
        self.project_number.setPlaceholderText("TTA-26-00000")
        layout.addWidget(self.project_number)

        metadata_buttons = QHBoxLayout()
        metadata_buttons.setSpacing(8)
        self.metadata_btn = QPushButton("GS 정보 확인")
        self.metadata_btn.clicked.connect(self.fetch_metadata)
        gs_search_btn = QPushButton("GS 검색")
        gs_search_btn.clicked.connect(self.open_reference_search)
        self.manual_metadata_btn = QPushButton("직접 입력")
        self.manual_metadata_btn.clicked.connect(self.enter_metadata_manually)
        metadata_buttons.addWidget(self.metadata_btn)
        metadata_buttons.addWidget(gs_search_btn)
        metadata_buttons.addWidget(self.manual_metadata_btn)
        layout.addLayout(metadata_buttons)

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(10)
        info_grid.setVerticalSpacing(8)
        fields = [
            ("회사명", "company"),
            ("제품명", "product"),
            ("PL", "pl"),
            ("WD", "wd"),
            ("인증일", "cert_date"),
            ("점검결과", "review"),
        ]
        for row, (label_text, attr_name) in enumerate(fields):
            key = QLabel(label_text)
            key.setStyleSheet(_label_style(C_MUTED, 11, 700))
            value = _value_label("—")
            setattr(self, attr_name, value)
            info_grid.addWidget(key, row, 0, Qt.AlignTop)
            info_grid.addWidget(value, row, 1, Qt.AlignTop)
        layout.addLayout(info_grid)

        self.period = _muted("시험기간 —")
        layout.addWidget(self.period)

        badges = QHBoxLayout()
        badges.setSpacing(8)
        self.action_status = QLabel("대기")
        self.action_status.setStyleSheet(_label_style(C_PRIMARY, 12, 800))
        self.rulebase_status = QLabel(self._rule_cache_text(self.rule_cache))
        self.rulebase_status.setStyleSheet(_label_style(C_MUTED, 11, 700))
        badges.addWidget(self.action_status)
        badges.addStretch()
        badges.addWidget(self.rulebase_status)
        layout.addLayout(badges)

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
        self.file_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.file_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.file_table.verticalScrollBar().setSingleStep(24)
        self.file_table.horizontalScrollBar().setSingleStep(24)
        layout.addWidget(self.file_table, stretch=1)
        return frame

    def _build_summary_row(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._stat_labels: dict[str, QLabel] = {}
        cards = [
            ("total", C_TEXT, C_SOFT, "전체 0"),
            ("pass", C_SUCCESS, C_SUCCESS_SOFT, "적합 0"),
            ("fail", C_DANGER, C_DANGER_SOFT, "부적합 0"),
            ("unsupported", C_MUTED, C_SOFT, "미지원 0"),
            ("error", C_WARNING, C_WARNING_SOFT, "오류 0"),
        ]
        for key, fg, bg, text in cards:
            card = _soft_card()
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(10)
            count = QLabel(text)
            count.setStyleSheet(_label_style(fg, 20, 800))
            badge = QLabel("점검 결과")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                f"background-color: {bg}; color: {fg}; border: none;"
                " border-radius: 5px; padding: 4px 10px;"
                " font-size: 11px; font-weight: 700;"
            )
            self._stat_labels[key] = count
            card_layout.addWidget(count)
            card_layout.addStretch()
            card_layout.addWidget(badge)
            layout.addWidget(card)
        return row

    def _build_result_panel(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(_section_title("결과 테이블"))

        self.result_table = QTableWidget(0, 6)
        self.result_table.setObjectName("resultTable")
        self.result_table.setHorizontalHeaderLabels(["번호", "결과", "점검항목", "기대값", "실제값", "메시지"])
        hdr = self.result_table.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.result_table.setColumnWidth(0, 70)
        self.result_table.setColumnWidth(1, 76)
        self.result_table.setColumnWidth(2, 230)
        self.result_table.setColumnWidth(3, 280)
        self.result_table.setColumnWidth(4, 280)
        self.result_table.setColumnWidth(5, 360)
        hdr.setStretchLastSection(False)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.verticalHeader().setDefaultSectionSize(48)
        self.result_table.verticalHeader().setMinimumSectionSize(40)
        self.result_table.setSortingEnabled(False)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setShowGrid(False)
        self.result_table.setWordWrap(True)
        self.result_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.result_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.result_table.verticalScrollBar().setSingleStep(24)
        self.result_table.horizontalScrollBar().setSingleStep(24)
        self.result_table.cellDoubleClicked.connect(self._show_result_detail)
        self.result_table.itemSelectionChanged.connect(self._update_result_detail_panel)
        layout.addWidget(self.result_table, stretch=1)
        return frame

    def _build_detail_panel(self) -> QFrame:
        frame = _panel()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(_section_title("선택한 항목 상세"))

        self.detail_status = QLabel("대기")
        self.detail_status.setAlignment(Qt.AlignCenter)
        self.detail_status.setFixedWidth(86)
        self.detail_status.setStyleSheet(
            f"background-color: {C_PRIMARY_SOFT}; color: {C_PRIMARY};"
            " border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 800;"
        )
        layout.addWidget(self.detail_status, alignment=Qt.AlignLeft)

        self.detail_title = QLabel("점검 결과 행을 선택하세요")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(_label_style(C_TEXT, 16, 800))
        layout.addWidget(self.detail_title)

        for heading, attr_name in [
            ("예상 값", "detail_expected"),
            ("실제 값", "detail_actual"),
            ("메시지", "detail_message"),
        ]:
            label = QLabel(heading)
            label.setStyleSheet(_label_style(C_MUTED, 11, 700))
            layout.addWidget(label)
            box = QLabel("-")
            box.setWordWrap(True)
            box.setMinimumHeight(58)
            box.setStyleSheet(
                f"background-color: #fbfdff; border: 1px solid {C_LINE};"
                " border-radius: 8px; padding: 12px;"
                f" color: {C_TEXT}; font-size: 12px; font-weight: 500;"
            )
            setattr(self, attr_name, box)
            layout.addWidget(box)

        layout.addStretch()
        hint = QLabel("행을 더블클릭하면 엔진 상세 근거를 팝업으로 확인할 수 있습니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet(_label_style(C_MUTED, 11, 500))
        layout.addWidget(hint)
        return frame

    def _set_metadata(self, metadata):
        super()._set_metadata(metadata)
        self._refresh_metadata_extras()

    def open_reference_search(self):
        super().open_reference_search()
        self._refresh_metadata_extras()

    def _refresh_metadata_extras(self):
        metadata = self.current_metadata
        if metadata is None:
            self.period.setText("시험기간 —")
            return
        start = metadata.start_date or "—"
        end = metadata.end_date or "—"
        self.period.setText(f"시험기간 {start} - {end}")

    def _set_file_rows(self, scan):
        super()._set_file_rows(scan)
        self.file_count_label.setText(f"파일 {scan.file_count}개 · {scan.total_size_mb} MB")

    def _set_result_rows(self, summary):
        table = self.result_table
        table.setSortingEnabled(False)
        table.clearContents()
        table.clearSpans()

        rows = self._dashboard_result_rows(summary)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            detail = row["detail"]
            status = detail.status
            fg, bg, label = STATUS_META.get(status, (C_TEXT, C_SOFT, status))
            self._put_dashboard_cell(row_index, 0, detail.display_number, detail, align=Qt.AlignCenter, fg=C_MUTED, bold=True)
            self._put_dashboard_cell(row_index, 1, label, detail, align=Qt.AlignCenter, fg=fg, bg=bg, bold=True)
            self._put_dashboard_cell(row_index, 2, row["item"], detail, bold=True)
            self._put_dashboard_cell(row_index, 3, detail.expected, detail)
            self._put_dashboard_cell(row_index, 4, detail.actual, detail)
            self._put_dashboard_cell(row_index, 5, detail.message, detail)

        counts = {PASS: 0, FAIL: 0, UNSUPPORTED: 0, ERROR: 0}
        for result in summary.results:
            counts[result.status] = counts.get(result.status, 0) + 1
        self._stat_labels["total"].setText(f"전체 {len(summary.results)}")
        self._stat_labels["pass"].setText(f"적합 {counts.get(PASS, 0)}")
        self._stat_labels["fail"].setText(f"부적합 {counts.get(FAIL, 0)}")
        self._stat_labels["unsupported"].setText(f"미지원 {counts.get(UNSUPPORTED, 0)}")
        self._stat_labels["error"].setText(f"오류 {counts.get(ERROR, 0)}")

        table.resizeRowsToContents()
        if self.result_table.rowCount() > 0:
            self.result_table.selectRow(0)
        self._update_result_detail_panel()

    def _dashboard_result_rows(self, summary):
        return [{"item": detail.rule_name, "detail": detail} for detail in build_display_rows(summary.results)]

    def _put_dashboard_cell(
        self,
        row: int,
        col: int,
        text: str,
        detail: DisplayResultRow,
        *,
        align=Qt.AlignLeft | Qt.AlignVCenter,
        fg: str | None = None,
        bg: str | None = None,
        bold: bool = False,
    ):
        item = QTableWidgetItem(text if text not in (None, "") else "-")
        item.setTextAlignment(align)
        item.setToolTip(item.text())
        item.setData(Qt.ItemDataRole.UserRole, detail)
        font = item.font()
        font.setPointSize(9)
        font.setBold(bold)
        item.setFont(font)
        item.setForeground(QColor(fg or (C_MUTED if item.text() == "-" else "#435064")))
        if bg:
            item.setBackground(QColor(bg))
        self.result_table.setItem(row, col, item)

    def _update_result_detail_panel(self):
        if not hasattr(self, "detail_title"):
            return
        row = self.result_table.currentRow()
        result = None
        if row >= 0:
            for col in range(self.result_table.columnCount()):
                item = self.result_table.item(row, col)
                if item is not None:
                    result = item.data(Qt.ItemDataRole.UserRole)
                    if result is not None:
                        break
        if result is None:
            self.detail_status.setText("대기")
            self.detail_status.setStyleSheet(
                f"background-color: {C_PRIMARY_SOFT}; color: {C_PRIMARY};"
                " border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 800;"
            )
            self.detail_title.setText("점검 결과 행을 선택하세요")
            self.detail_expected.setText("-")
            self.detail_actual.setText("-")
            self.detail_message.setText("-")
            return

        fg, bg, label = STATUS_META.get(result.status, (C_TEXT, C_SOFT, result.status))
        self.detail_status.setText(label)
        self.detail_status.setStyleSheet(
            f"background-color: {bg}; color: {fg};"
            " border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 800;"
        )
        self.detail_title.setText(result.rule_name or "-")
        self.detail_expected.setText(result.expected or "-")
        self.detail_actual.setText(result.actual or "-")
        self.detail_message.setText(result.message or "-")


def main() -> int:
    app = QApplication([])
    app.setStyleSheet(APP_QSS)
    window = DashboardWindow()
    window.show()
    return app.exec()
