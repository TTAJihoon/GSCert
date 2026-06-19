from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiClientError, GSCertApiClient, ProjectMetadata
from .project import infer_project_number
from .rule_cache import RuleCacheSummary, load_rule_cache, save_rule_cache
from .scanner import FolderScan, scan_folder


DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GSCert Local Review")
        self.resize(1120, 760)
        self.selected_folder: Path | None = None
        self.scan: FolderScan | None = None
        self.rule_cache = load_rule_cache()

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._build_connection_box())
        layout.addWidget(self._build_rulebase_box())
        layout.addWidget(self._build_folder_box())
        layout.addWidget(self._build_metadata_box())
        layout.addWidget(self._build_file_table(), stretch=1)
        self.setCentralWidget(root)

    def _build_connection_box(self) -> QGroupBox:
        box = QGroupBox("Server")
        layout = QGridLayout(box)

        self.server_url = QLineEdit(DEFAULT_SERVER_URL)
        self.center = QComboBox()
        self.center.addItem("상암", "sangam")
        self.center.addItem("영남", "yeongnam")
        health_button = QPushButton("연결 확인")
        health_button.clicked.connect(self.check_health)

        layout.addWidget(QLabel("URL"), 0, 0)
        layout.addWidget(self.server_url, 0, 1)
        layout.addWidget(QLabel("센터"), 0, 2)
        layout.addWidget(self.center, 0, 3)
        layout.addWidget(health_button, 0, 4)
        layout.setColumnStretch(1, 1)
        return box

    def _build_rulebase_box(self) -> QGroupBox:
        box = QGroupBox("Rulebase")
        layout = QGridLayout(box)

        self.rulebase_status = QLabel(self._rule_cache_text(self.rule_cache))
        manifest_button = QPushButton("규칙 버전 확인")
        manifest_button.clicked.connect(self.check_rule_manifest)
        update_button = QPushButton("규칙 업데이트")
        update_button.clicked.connect(self.update_rules)

        layout.addWidget(QLabel("현재 규칙"), 0, 0)
        layout.addWidget(self.rulebase_status, 0, 1)
        layout.addWidget(manifest_button, 0, 2)
        layout.addWidget(update_button, 0, 3)
        layout.setColumnStretch(1, 1)
        return box

    def _build_folder_box(self) -> QGroupBox:
        box = QGroupBox("Local Folder")
        layout = QGridLayout(box)

        self.folder_path = QLineEdit()
        self.folder_path.setReadOnly(True)
        browse_button = QPushButton("폴더 선택")
        browse_button.clicked.connect(self.choose_folder)

        self.project_number = QLineEdit()
        metadata_button = QPushButton("기준정보 조회")
        metadata_button.clicked.connect(self.fetch_metadata)
        scan_button = QPushButton("파일 스캔")
        scan_button.clicked.connect(self.scan_files)

        layout.addWidget(QLabel("폴더"), 0, 0)
        layout.addWidget(self.folder_path, 0, 1)
        layout.addWidget(browse_button, 0, 2)
        layout.addWidget(QLabel("프로젝트 번호"), 1, 0)
        layout.addWidget(self.project_number, 1, 1)
        layout.addWidget(metadata_button, 1, 2)
        layout.addWidget(scan_button, 1, 3)
        layout.setColumnStretch(1, 1)
        return box

    def _build_metadata_box(self) -> QGroupBox:
        box = QGroupBox("Project Metadata")
        layout = QHBoxLayout(box)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self.company = QLabel("-")
        self.product = QLabel("-")
        self.pl = QLabel("-")
        self.wd = QLabel("-")
        self.cert_date = QLabel("-")
        self.review = QLabel("-")
        form.addRow("회사명", self.company)
        form.addRow("제품명", self.product)
        form.addRow("PL", self.pl)
        form.addRow("WD", self.wd)
        form.addRow("인증일", self.cert_date)
        form.addRow("점검결과", self.review)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(110)

        layout.addWidget(form_widget, stretch=1)
        layout.addWidget(self.summary, stretch=2)
        return box

    def _build_file_table(self) -> QTableWidget:
        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(["파일명", "상대 경로", "확장자", "크기(bytes)"])
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.setSortingEnabled(True)
        return self.file_table

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
        cached_version = self.rule_cache.rulebase_version or "(없음)"
        server_version = manifest.get("rulebase_version") or "(없음)"
        QMessageBox.information(
            self,
            "규칙 버전 확인",
            "\n".join(
                [
                    f"서버 규칙 버전: {server_version}",
                    f"로컬 규칙 버전: {cached_version}",
                    f"규칙 개수: {manifest.get('rule_count', 0)}",
                    f"필요 엔진 버전: {manifest.get('engine_min_version', '')}",
                ]
            ),
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
        folder_text = self.folder_path.text().strip()
        if not folder_text:
            self._show_error("먼저 점검 대상 폴더를 선택하세요.")
            return
        folder = Path(folder_text)
        if not folder.is_dir():
            self._show_error("선택한 폴더가 존재하지 않습니다.")
            return
        self.scan = scan_folder(folder)
        self._set_file_rows(self.scan)
        self.summary.setPlainText(
            f"폴더: {folder}\n파일 수: {self.scan.file_count}\n전체 크기: {self.scan.total_size_mb} MB"
        )

    def _client(self) -> GSCertApiClient:
        return GSCertApiClient(self.server_url.text().strip() or DEFAULT_SERVER_URL)

    def _rule_cache_text(self, summary: RuleCacheSummary) -> str:
        if not summary.exists:
            return "로컬 규칙 없음"
        return f"{summary.rulebase_version} / {summary.rule_count}개 / {summary.path}"

    def _set_metadata(self, metadata: ProjectMetadata):
        self.company.setText(metadata.company_name or "-")
        self.product.setText(metadata.product_name or "-")
        self.pl.setText(metadata.pl_name or "-")
        self.wd.setText(metadata.wd_name or "-")
        self.cert_date.setText(metadata.cert_date or "-")
        self.review.setText(metadata.review or "-")
        self.summary.setPlainText(
            "\n".join(
                [
                    f"프로젝트 번호: {metadata.project_number}",
                    f"회사명: {metadata.company_name}",
                    f"제품명: {metadata.product_name}",
                    f"PL: {metadata.pl_name}",
                    f"WD: {metadata.wd_name}",
                    f"신청일: {metadata.request_date}",
                    f"계약일: {metadata.contract_date}",
                    f"인증일: {metadata.cert_date}",
                    f"시험 시작일: {metadata.start_date or '(서버 미제공)'}",
                    f"시험 종료일: {metadata.end_date or '(서버 미제공)'}",
                ]
            )
        )

    def _set_file_rows(self, scan: FolderScan):
        self.file_table.setSortingEnabled(False)
        self.file_table.setRowCount(len(scan.files))
        for row, file in enumerate(scan.files):
            values = [file.name, file.relative_path, file.extension, str(file.size_bytes)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.file_table.setItem(row, column, item)
        self.file_table.resizeColumnsToContents()
        self.file_table.setSortingEnabled(True)

    def _show_error(self, message: str):
        QMessageBox.warning(self, "GSCert Local Review", message)


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
