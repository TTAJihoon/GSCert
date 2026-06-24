"""점검 산출물(캡처 이미지·다운로드 파일) 저장 추상화.

웹은 PDF 1페이지/Excel 영역 캡처를 DB·디스크에 저장해 UI에 표시하지만,
로컬 검토 프로그램은 PASS/FAIL 판정만 필요하므로 산출물을 저장하지 않는다.
엔진은 이 인터페이스를 통해서만 산출물을 생성하고, 어댑터가 구현을 주입한다.
"""

from __future__ import annotations

from typing import Any, Protocol


class ArtifactSink(Protocol):
    """엔진이 산출물을 넘기는 대상. 반환값은 raw_detail에 들어갈 dict."""

    def store_pdf_first_page(
        self, project: Any, rule: Any, file: Any, *, artifact_id: str, label: str
    ) -> dict[str, Any]:
        ...

    def store_pdf_download(
        self, project: Any, rule: Any, file: Any, *, artifact_id: str, label: str
    ) -> dict[str, Any]:
        ...

    def store_excel_area(
        self,
        project: Any,
        rule: Any,
        sheet: Any,
        area: Any,
        *,
        artifact_id: str,
        label: str,
        source_file: str,
    ) -> dict[str, Any]:
        ...


class NoOpArtifactSink:
    """산출물을 만들지 않는 sink (로컬 검토 프로그램용).

    엔진이 산출물 생성을 시도해도 메타데이터만 돌려주고 파일은 만들지 않는다.
    """

    def store_pdf_first_page(self, project, rule, file, *, artifact_id, label):
        return {"id": artifact_id, "label": label, "skipped": True}

    def store_pdf_download(self, project, rule, file, *, artifact_id, label):
        return {"id": artifact_id, "label": label, "skipped": True}

    def store_excel_area(self, project, rule, sheet, area, *, artifact_id, label, source_file):
        return {"id": artifact_id, "label": label, "skipped": True}
