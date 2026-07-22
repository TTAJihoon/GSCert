"""GSCertLocalReviewDashboard.exe 실행 시 뜨는 스플래시 이미지(assets/splash.png)를 생성한다.

PyInstaller 는 --splash 옵션에 넘길 정적 이미지가 필요하다. 브랜딩(색상/폰트)이 바뀌면
이 스크립트를 다시 실행해서 assets/splash.png 를 재생성한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPixmap,
)

FONT_FILE = "C:/Windows/Fonts/malgun.ttf"

WIDTH, HEIGHT = 480, 280
C_BG = "#0f172a"
C_ACCENT = "#2563eb"
C_ACCENT_SOFT = "#60a5fa"
C_TEXT = "#f8fafc"
C_MUTED = "#94a3b8"


def build_pixmap(font_family: str) -> QPixmap:
    pixmap = QPixmap(WIDTH, HEIGHT)
    pixmap.fill(QColor(C_BG))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, WIDTH, HEIGHT)
    gradient.setColorAt(0.0, QColor(C_BG))
    gradient.setColorAt(1.0, QColor("#111c34"))
    painter.fillRect(0, 0, WIDTH, HEIGHT, gradient)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(C_ACCENT))
    painter.drawRect(0, 0, WIDTH, 6)

    painter.setPen(QColor(C_TEXT))
    title_font = QFont(font_family)
    title_font.setPixelSize(26)
    title_font.setWeight(QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.drawText(QRectF(36, 96, WIDTH - 72, 40), Qt.AlignmentFlag.AlignLeft, "GSCert Local Review")

    painter.setPen(QColor(C_ACCENT_SOFT))
    subtitle_font = QFont(font_family)
    subtitle_font.setPixelSize(14)
    painter.setFont(subtitle_font)
    painter.drawText(QRectF(36, 140, WIDTH - 72, 28), Qt.AlignmentFlag.AlignLeft, "산출물 점검 데스크톱 앱")

    painter.setPen(QColor(C_MUTED))
    loading_font = QFont(font_family)
    loading_font.setPixelSize(13)
    painter.setFont(loading_font)
    painter.drawText(
        QRectF(36, HEIGHT - 56, WIDTH - 72, 24),
        Qt.AlignmentFlag.AlignLeft,
        "불러오는 중입니다. 잠시만 기다려 주세요...",
    )

    painter.end()
    return pixmap


def main() -> int:
    app = QGuiApplication(sys.argv)

    font_family = "Malgun Gothic"
    font_id = QFontDatabase.addApplicationFont(FONT_FILE)
    if font_id != -1:
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            font_family = families[0]
    else:
        print(f"[WARN] 폰트를 불러오지 못했습니다: {FONT_FILE} (기본 폰트로 대체)", file=sys.stderr)

    pixmap = build_pixmap(font_family)
    out_path = Path(__file__).resolve().parents[1] / "assets" / "splash.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(out_path), "PNG"):
        print(f"[ERROR] 스플래시 이미지 저장 실패: {out_path}", file=sys.stderr)
        return 1
    print(f"[OK] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
