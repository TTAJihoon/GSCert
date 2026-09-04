from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from . import cert_trust


class ApiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReferenceItem:
    serial_number: int = 0
    cert_number: str = ""
    cert_date: str = ""
    company: str = ""
    product: str = ""
    grade: str = ""
    test_number: str = ""
    sw_category: str = ""
    start_date: str = ""
    end_date: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReferenceItem":
        return cls(
            serial_number=int(d.get("serial_number") or 0),
            cert_number=str(d.get("cert_number") or ""),
            cert_date=str(d.get("cert_date") or ""),
            company=str(d.get("company") or ""),
            product=str(d.get("product") or ""),
            grade=str(d.get("grade") or ""),
            test_number=str(d.get("test_number") or ""),
            sw_category=str(d.get("sw_category") or ""),
            start_date=str(d.get("start_date") or ""),
            end_date=str(d.get("end_date") or ""),
        )


@dataclass(frozen=True)
class ProjectMetadata:
    project_number: str = ""
    company_name: str = ""
    product_name: str = ""
    pl_name: str = ""
    wd_name: str = ""
    request_date: str = ""
    contract_date: str = ""
    cert_date: str = ""
    start_date: str = ""
    end_date: str = ""
    review: str = ""
    center_code: str = ""
    center_label: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ProjectMetadata":
        project = payload.get("project") or {}
        return cls(
            project_number=str(project.get("project_number") or ""),
            company_name=str(project.get("company_name") or ""),
            product_name=str(project.get("product_name") or ""),
            pl_name=str(project.get("pl_name") or ""),
            wd_name=str(project.get("wd_name") or ""),
            request_date=str(project.get("request_date") or ""),
            contract_date=str(project.get("contract_date") or ""),
            cert_date=str(project.get("cert_date") or ""),
            start_date=str(project.get("start_date") or ""),
            end_date=str(project.get("end_date") or ""),
            review=str(project.get("review") or ""),
            center_code=str(project.get("center_code") or ""),
            center_label=str(project.get("center_label") or ""),
        )


class GSCertApiClient:
    def __init__(self, base_url: str, timeout_seconds: int = 60, token: str = ""):
        # 규칙 번들이 커질 수 있어 기본 타임아웃을 넉넉히 둔다(과거 10초는 빠듯).
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.token = (token or "").strip()
        # 서버가 자체서명 https 인증서를 쓰므로, OS 신뢰 저장소 대신 번들 인증서에 핀 고정한다
        # (신뢰 저장소 등록은 관리자 권한이 필요해 리뷰어 PC에서 못 쓸 때가 많다).
        self._ssl_context = cert_trust.build_ssl_context()

    def health(self) -> dict[str, Any]:
        return self._get_json("/api/local-review/health/")

    def project_metadata(self, project_number: str, center: str = "") -> ProjectMetadata:
        # center 미지정 → 서버가 전체 센터에서 프로젝트번호로 조회한다(센터 무관).
        quoted_number = quote(project_number.strip())
        query = urlencode({"center": center}) if center else ""
        suffix = f"?{query}" if query else ""
        payload = self._get_json(f"/api/local-review/projects/{quoted_number}/metadata/{suffix}")
        return ProjectMetadata.from_payload(payload)

    def rule_manifest(self) -> dict[str, Any]:
        return self._get_json("/api/local-review/rules/manifest/")

    def search_reference(self, q: str, limit: int = 20) -> list[ReferenceItem]:
        query = urlencode({"q": q.strip(), "limit": limit})
        payload = self._get_json(f"/api/reference/search/?{query}")
        return [ReferenceItem.from_dict(item) for item in (payload.get("items") or [])]

    def rule_bundle(self, version: str = "") -> dict[str, Any]:
        query = urlencode({"version": version}) if version else ""
        suffix = f"?{query}" if query else ""
        return self._get_json(f"/api/local-review/rules/bundle/{suffix}")

    def download_app_package(self, dest_path: Path) -> None:
        """로컬 앱 자체 업데이트용 zip 패키지를 dest_path 에 내려받는다."""
        url = f"{self.base_url}/api/local-review/app/download/"
        headers = {}
        if self.token:
            headers["X-Local-Review-Token"] = self.token
        request = Request(url, headers=headers)
        try:
            # 앱 패키지는 규칙 번들보다 훨씬 커서(수십 MB) 넉넉한 타임아웃을 쓴다.
            with urlopen(request, timeout=max(self.timeout_seconds, 300), context=self._ssl_context) as response:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as file_obj:
                    shutil.copyfileobj(response, file_obj)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            message = _message_from_error_body(detail) or exc.reason
            raise ApiClientError(f"API error {exc.code}: {message}") from exc
        except URLError as exc:
            raise ApiClientError(f"Cannot connect to server: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ApiClientError("Server request timed out.") from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-Local-Review-Token"] = self.token
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            message = _message_from_error_body(detail) or exc.reason
            raise ApiClientError(f"API error {exc.code}: {message}") from exc
        except URLError as exc:
            raise ApiClientError(f"Cannot connect to server: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ApiClientError("Server request timed out.") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ApiClientError("Server returned an invalid JSON response.") from exc

        if payload.get("success") is False:
            raise ApiClientError(str(payload.get("message") or "Server request failed."))
        return payload


def _message_from_error_body(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()
    return str(payload.get("message") or "").strip()
