"""Token-budgeted product overview generation for one multi-file product."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from main.utils.gemini_gemma import (
    GemmaGenerationError,
    count_gemma_tokens,
    extract_json_object,
    generate_gemma_text,
)
from .similar_documents import DocumentUnit, ParsedDocument, deduplicate_units


logger = logging.getLogger(__name__)

DIRECT_TOKEN_LIMIT = 20_000
CHUNK_TARGET_TOKENS = 6_000
MAX_CANDIDATE_CHARS = 4_000_000
MAX_LLM_SELECTED_CHARS = 1_200_000
MAX_FINAL_CONTEXT_TOKENS = 80_000


@dataclass
class AnalysisCoverage:
    file_count: int
    successful_files: int
    failed_files: int
    extracted_units: int
    selected_units: int
    duplicate_units: int
    extracted_chars: int
    selected_chars: int
    input_tokens: int
    llm_input_tokens: int
    llm_output_tokens: int
    llm_total_tokens: int
    llm_call_count: int
    strategy: str
    truncated: bool

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class LlmTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0

    def add(self, usage: dict):
        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
        self.output_tokens += int(usage.get("output_tokens", 0) or 0)
        self.total_tokens += int(usage.get("total_tokens", 0) or 0)
        self.call_count += 1


def _pack_units(units: list[DocumentUnit], target_tokens: int):
    target_chars = target_tokens * 4
    chunks = []
    current = []
    size = 0
    for unit in units:
        block = f"[{unit.source_id}]\n{unit.text}".strip()
        if current and size + len(block) > target_chars:
            chunks.append("\n\n".join(current))
            current = []
            size = 0
        # Keep source boundaries. Very large units are split only on lines.
        if len(block) > target_chars:
            for line in block.splitlines():
                if current and size + len(line) > target_chars:
                    chunks.append("\n\n".join(current))
                    current = []
                    size = 0
                current.append(line)
                size += len(line)
        else:
            current.append(block)
            size += len(block)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _select_units(units: list[DocumentUnit]):
    """Inspect all units, then retain a relevance- and coverage-balanced subset."""
    keywords = (
        "기능",
        "제공",
        "사용자",
        "시스템",
        "소프트웨어",
        "솔루션",
        "관리",
        "처리",
        "검색",
        "분석",
        "연동",
        "지원",
        "서비스",
        "데이터",
        "보안",
    )
    scored = []
    file_seen = {}
    candidate_chars = 0
    candidate_truncated = False
    for order, unit in enumerate(units):
        if candidate_chars + len(unit.text) > MAX_CANDIDATE_CHARS:
            candidate_truncated = True
            break
        candidate_chars += len(unit.text)
        count_in_file = file_seen.get(unit.filename, 0)
        file_seen[unit.filename] = count_in_file + 1
        score = sum(unit.text.count(keyword) for keyword in keywords)
        if unit.kind in {"paragraph", "section", "text", "notes"}:
            score += 2
        if count_in_file < 3:
            score += 20
        score += min(len(unit.text), 1000) / 1000
        scored.append((score, order, unit))

    if candidate_chars <= MAX_LLM_SELECTED_CHARS:
        return [item[2] for item in scored], candidate_truncated

    chosen = []
    chosen_chars = 0
    for _, order, unit in sorted(scored, key=lambda item: (-item[0], item[1])):
        if chosen_chars + len(unit.text) > MAX_LLM_SELECTED_CHARS:
            continue
        chosen.append((order, unit))
        chosen_chars += len(unit.text)
    chosen.sort(key=lambda item: item[0])
    return [item[1] for item in chosen], True


def _map_chunk(
    chunk: str,
    index: int,
    total: int,
    usage: LlmTokenUsage | None = None,
) -> str:
    prompt = f"""
여러 문서가 모두 하나의 동일한 소프트웨어 제품을 설명한다.
아래는 문서 묶음 {index}/{total}이다. 제품 개요 작성에 필요한 사실만 압축하라.

규칙:
- 목적, 핵심 기능, 대상 사용자/업무, 기술·연동·배포 방식, 중요 제한을 보존한다.
- 제품명·회사명·광고 문구·목차·반복 설명은 제외한다.
- 부정 표현과 고유 기술 용어는 바꾸지 않는다.
- 각 사실 끝에 근거 source_id를 괄호로 붙인다.
- 최대 12개 불릿, 불릿당 한 문장으로 반환한다.

문서:
{chunk}
"""
    return generate_gemma_text(
        prompt,
        usage_callback=usage.add if usage else None,
    )


def _final_options(
    context: str,
    max_chars: int = 60,
    usage: LlmTokenUsage | None = None,
):
    prompt = f"""
아래 자료는 하나의 동일한 소프트웨어 제품에 관한 문서에서 추출한 내용이다.
자료에만 근거해 유사 제품 검색용 제품 개요 문장 5개를 만든다.

반환 항목:
- original_summary: 자료 전체를 가장 충실하게 대표하는 제품 개요 1개
- recommendations: 같은 핵심 목적과 기능을 유지하되 표현과 강조점만 달리한 추천 문장 4개

규칙:
1. 모든 문장은 공백 포함 {max_chars}자 이내의 완결된 한국어 한 문장이다.
2. 다섯 문장 모두 동일 제품의 핵심 목적·기능을 공유해야 한다.
3. 자료에 없는 기능이나 기술을 만들지 않는다.
4. 제품명과 회사명은 제외한다.
5. "~을 제공하는 ~솔루션/시스템/프로그램" 형태를 우선한다.
6. 서로 중복되는 문장은 만들지 않는다.
7. 설명이나 마크다운 없이 아래 JSON 객체만 반환한다.

{{"original_summary":"문장","recommendations":["문장1","문장2","문장3","문장4"]}}

자료:
{context}
"""
    parsed = extract_json_object(
        generate_gemma_text(
            prompt,
            usage_callback=usage.add if usage else None,
        )
    )
    if not isinstance(parsed, dict):
        raise GemmaGenerationError("제품 개요 응답 JSON을 해석할 수 없습니다.")

    def clean(value):
        return " ".join(str(value or "").split())[:max_chars].strip()

    original = clean(parsed.get("original_summary"))
    raw_recommendations = parsed.get("recommendations")
    if not original or not isinstance(raw_recommendations, list):
        raise GemmaGenerationError("제품 개요 응답 항목이 올바르지 않습니다.")
    recommendations = []
    seen = {original}
    for value in raw_recommendations:
        item = clean(value)
        if item and item not in seen:
            recommendations.append(item)
            seen.add(item)
    if len(recommendations) != 4:
        raise GemmaGenerationError("서로 다른 추천 제품 개요 4개를 생성하지 못했습니다.")
    return original, recommendations


def analyze_documents(
    documents: list[ParsedDocument],
    *,
    failed_files: int = 0,
    max_chars: int = 60,
):
    usage = LlmTokenUsage()
    extracted_chars = sum(
        len(unit.text)
        for document in documents
        for unit in document.units
    )
    units, duplicate_count = deduplicate_units(documents)
    selected, truncated = _select_units(units)
    selected_chars = sum(len(unit.text) for unit in selected)
    if not selected:
        raise GemmaGenerationError("분석할 제품 설명 텍스트가 없습니다.")

    direct_context = "\n\n".join(
        f"[{unit.source_id}]\n{unit.text}" for unit in selected
    )
    token_count = count_gemma_tokens(direct_context)
    if token_count <= DIRECT_TOKEN_LIMIT:
        final_context = direct_context
        strategy = "direct"
    else:
        chunks = _pack_units(selected, CHUNK_TARGET_TOKENS)
        mapped = [
            _map_chunk(chunk, index, len(chunks), usage)
            for index, chunk in enumerate(chunks, 1)
        ]
        final_context = "\n\n".join(
            f"[문서 묶음 요약 {index}]\n{text}" for index, text in enumerate(mapped, 1)
        )
        final_tokens = count_gemma_tokens(final_context)
        strategy = "map-reduce"
        if final_tokens > MAX_FINAL_CONTEXT_TOKENS:
            # A second reduce pass keeps all first-pass summaries represented.
            reduce_chunks = _pack_text(final_context, CHUNK_TARGET_TOKENS)
            reduced_chunks = [
                _map_chunk(chunk, index, len(reduce_chunks), usage)
                for index, chunk in enumerate(reduce_chunks, 1)
            ]
            final_context = "\n\n".join(reduced_chunks)
            strategy = "map-tree-reduce"

    original, recommendations = _final_options(
        final_context,
        max_chars=max_chars,
        usage=usage,
    )
    coverage = AnalysisCoverage(
        file_count=len(documents) + failed_files,
        successful_files=len(documents),
        failed_files=failed_files,
        extracted_units=len(units) + duplicate_count,
        selected_units=len(selected),
        duplicate_units=duplicate_count,
        extracted_chars=extracted_chars,
        selected_chars=selected_chars,
        input_tokens=token_count,
        llm_input_tokens=usage.input_tokens,
        llm_output_tokens=usage.output_tokens,
        llm_total_tokens=usage.total_tokens,
        llm_call_count=usage.call_count,
        strategy=strategy,
        truncated=truncated,
    )
    logger.info("Similar document analysis coverage: %s", coverage.to_dict())
    return original, recommendations, coverage


def _pack_text(text: str, target_tokens: int):
    target_chars = target_tokens * 4
    paragraphs = re.split(r"\n{2,}", text)
    chunks = []
    current = []
    size = 0
    for paragraph in paragraphs:
        if current and size + len(paragraph) > target_chars:
            chunks.append("\n\n".join(current))
            current = []
            size = 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        chunks.append("\n\n".join(current))
    return chunks
