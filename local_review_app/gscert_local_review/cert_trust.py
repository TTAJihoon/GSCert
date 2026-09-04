"""GSCert 서버 https 연결의 인증서 신뢰 설정.

서버는 두 가지 방식으로 서비스된 적이 있다:
1. IP 주소(210.96.71.194) + 자체서명 인증서 — 일반 브라우저/OS가 기본적으로
   신뢰하지 않는다. Windows "신뢰할 수 있는 루트 인증 기관" 저장소에 등록하려면
   관리자 권한이 필요한데(certutil -addstore 는 일반 사용자 계정에서는
   ERROR_ACCESS_DENIED), 리뷰어 PC 대부분이 비관리자 계정이라 등록이 불가능했다.
   그래서 이 exe 에 함께 배포된 인증서(certs/gscert.crt)를 직접 신뢰하도록
   SSLContext 에 추가해뒀다(핀 고정).
2. 정식 도메인(gsai.tta.or.kr) + Let's Encrypt 발급 인증서 — 공인 CA(ISRG Root X1)
   체인이라 OS 기본 신뢰 저장소만으로 정상 검증된다. 별도 조치가 필요 없다.

이전 구현은 `ssl.create_default_context(cafile=gscert.crt)` 로 만들어서 *그
인증서 하나만* 신뢰하는 컨텍스트를 썼는데, 이러면 OS 기본 신뢰 저장소가 통째로
무시된다. 그 결과 도메인 기본값을 gsai.tta.or.kr 로 바꾸자 "unable to get local
issuer certificate" 오류가 났다 — Let's Encrypt 체인이 이 컨텍스트에는 전혀
없었기 때문이다(자체서명 인증서 하나만 들어있었으므로). 지금은 OS 기본
신뢰 저장소를 그대로 두고 그 위에 사내 자체서명 인증서를 "추가"만 해서, 두
방식(IP 자체서명 / 정식 도메인) 모두 동작하게 한다.
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
    """OS 기본 신뢰 저장소(공인 CA)에 사내 자체서명 인증서를 추가한 SSLContext 를 만든다.

    OS 기본 CA는 그대로 유지되므로 정식 도메인(gsai.tta.or.kr, Let's Encrypt)은
    평소처럼 검증되고, 번들 인증서(certs/gscert.crt)가 있으면 예전 IP 기반
    자체서명 엔드포인트도 추가로 신뢰한다. 번들 인증서가 없거나 로드에 실패해도
    OS 기본 검증은 그대로 동작해야 하므로 이 함수가 None 을 반환하는 일은 없다
    (urlopen 에 context=None 을 넘긴 것과 동일하게 동작).
    """
    context = ssl.create_default_context()
    cert_path = bundled_cert_path()
    if cert_path.exists():
        try:
            context.load_verify_locations(cafile=str(cert_path))
        except (OSError, ssl.SSLError):
            pass
    return context
