"""GSCert 서버(nginx)의 자체서명 https 인증서를 API 클라이언트에서 신뢰하기 위한 유틸리티.

서버 인증서를 Windows "신뢰할 수 있는 루트 인증 기관" 저장소에 등록하려면 관리자
권한이 필요하다(certutil -addstore 는 일반 사용자 계정에서는 ERROR_ACCESS_DENIED 로
실패한다). 리뷰어 PC 대부분이 비관리자 계정이므로, OS 저장소를 건드리는 대신
api_client.py 가 이 exe 에 함께 배포된 인증서(certs/gscert.crt) 하나만 직접
신뢰하도록 SSLContext 를 구성한다(인증서 핀 고정). 관리자 권한이 전혀 필요 없고,
시스템 전역 신뢰를 넓히지 않아 더 안전하다.

서버에서 인증서가 재발급되면 certs/gscert.crt 를 갱신하고 앱을 재빌드/재배포하면
된다(각 PC에서 별도 등록 작업 불필요).
"""
from __future__ import annotations

import ssl
import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """개발 모드(리포지토리 실행)와 PyInstaller 배포본(onedir/onefile) 모두에서 동작하는 경로 계산.

    PyInstaller 는 번들 데이터의 실제 위치를 `sys._MEIPASS` 에 넣어준다(onedir 에서는
    기본적으로 exe 옆의 `_internal` 폴더). exe 옆 폴더를 직접 가정하면 안 된다.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
    else:
        base = Path(__file__).resolve().parents[1]
    return base.joinpath(*parts)


def bundled_cert_path() -> Path:
    return resource_path("certs", "gscert.crt")


def build_ssl_context() -> ssl.SSLContext | None:
    """번들 인증서로 핀 고정된 SSLContext 를 만든다. 파일이 없으면 None(기본 동작으로 대체)."""
    cert_path = bundled_cert_path()
    if not cert_path.exists():
        return None
    try:
        return ssl.create_default_context(cafile=str(cert_path))
    except (OSError, ssl.SSLError):
        return None
