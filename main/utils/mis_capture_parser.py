"""MIS 업무 요청 캡처(HAR) 분석용 파서.

MIS는 HTTPS라서 패킷을 그대로 캡처해도 페이로드가 암호화되어 있어 그 자체로는
분석할 수 없다(복호화하려면 TLS 레코드 파싱이 필요해 Wireshark를 재구현하는
셈이 된다). 반면 브라우저 개발자도구가 저장하는 HAR은 이미 복호화된 요청/응답
본문을 담고 있으므로, 이 스크립트는 패킷 대신 HAR 파일(또는 DevTools에서 복사한
평문 한 조각)을 입력받아 SSV 구분자(0x1e=행, 0x1f=필드)로 split한 뒤 사람이
읽거나 Claude에게 그대로 넘길 수 있는 리포트를 만든다.

사용법:
    python mis_capture_parser.py <입력파일.har 또는 .txt> [-o 출력파일.md]

입력이 유효한 HAR(JSON)이면 각 요청을 시간순으로 나열하고, 그 중 SSV 구분자가
있는 요청/응답은 행/열로 분해해서 보여준다. HAR이 아니라 평문 텍스트 한 조각이면
그 내용 자체를 바로 split한다.
"""
import argparse
import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

ROW_SEP = "\x1e"
FIELD_SEP = "\x1f"


def split_ssv(text):
    """텍스트를 행(0x1e)/필드(0x1f) 구분자로 분해한다. 구분자가 없으면 None."""
    if ROW_SEP not in text and FIELD_SEP not in text:
        return None
    rows = [row for row in text.split(ROW_SEP) if row != ""]
    return [row.split(FIELD_SEP) for row in rows]


def format_table(rows, indent="    "):
    lines = []
    for i, row in enumerate(rows):
        lines.append(f"{indent}row[{i}] ({len(row)}열): {row}")
    return "\n".join(lines)


def decode_har_content(entry_content):
    """HAR response.content를 텍스트로 디코딩. base64 인코딩이면 해제."""
    text = entry_content.get("text")
    if text is None:
        return ""
    if entry_content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8", errors="replace")
        except Exception:
            return "(base64 디코딩 실패)"
    return text


def extract_pgm_svc(url, post_text, post_mime):
    """URL 쿼리스트링과 form 인코딩된 postData에서 pgmId/svcId를 찾는다."""
    params = dict(parse_qsl(urlsplit(url).query))
    if post_text and post_mime and "x-www-form-urlencoded" in post_mime:
        params.update(dict(parse_qsl(post_text)))
    return params.get("pgmId", "-"), params.get("svcId", "-")


def analyze_har(data):
    entries = data.get("log", {}).get("entries", [])
    summary_lines = []
    detail_blocks = []

    for i, entry in enumerate(entries):
        request = entry.get("request", {})
        response = entry.get("response", {})
        method = request.get("method", "-")
        url = request.get("url", "-")
        status = response.get("status", "-")
        started = entry.get("startedDateTime", "-")

        post_data = request.get("postData", {})
        post_text = post_data.get("text")
        post_mime = post_data.get("mimeType", "")

        content = response.get("content", {})
        resp_text = decode_har_content(content)

        pgm_id, svc_id = extract_pgm_svc(url, post_text, post_mime)

        summary_lines.append(
            f"[{i}] {started}  {method:6s} {status}  pgmId={pgm_id} svcId={svc_id}  {url}"
        )

        req_rows = split_ssv(post_text) if post_text else None
        resp_rows = split_ssv(resp_text) if resp_text else None

        if req_rows is None and resp_rows is None:
            continue  # SSV 구분자가 없는 요청(정적 리소스 등)은 상세 생략

        block = [f"### [{i}] {method} {url}", f"- 시각: {started}", f"- pgmId={pgm_id} svcId={svc_id}"]
        if req_rows is not None:
            block.append(f"- Request Payload ({len(req_rows)}행)")
            block.append(format_table(req_rows))
        elif post_text:
            block.append(f"- Request Payload (구분자 없음, 원문 일부): {post_text[:300]}")

        if resp_rows is not None:
            block.append(f"- Response ({len(resp_rows)}행)")
            block.append(format_table(resp_rows))
        elif resp_text:
            block.append(f"- Response (구분자 없음, 원문 일부): {resp_text[:300]}")

        detail_blocks.append("\n".join(block))

    return summary_lines, detail_blocks


def analyze_plain_text(text):
    rows = split_ssv(text)
    if rows is None:
        return None
    return format_table(rows)


def build_report(source_path, summary_lines, detail_blocks, plain_result):
    lines = [f"# MIS 요청 분석 리포트: {source_path.name}", ""]
    if plain_result is not None:
        lines.append("## Split 결과 (평문 입력)")
        lines.append(plain_result)
        return "\n".join(lines)

    lines.append("## 요청 순서 요약")
    lines.append("(조회/저장/재조회/확정 등 내부적으로 연달아 발생한 요청 순서 확인용)")
    lines.append("")
    lines.extend(summary_lines)
    lines.append("")
    lines.append("## 상세 (SSV 구분자가 있는 요청만)")
    lines.append("")
    lines.extend(detail_blocks)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="HAR(.har) 또는 평문(.txt) 파일 경로")
    parser.add_argument("-o", "--output", help="출력 리포트 경로(기본: <입력파일명>_analysis.md)")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"파일을 찾을 수 없습니다: {src}", file=sys.stderr)
        sys.exit(1)

    raw = src.read_text(encoding="utf-8", errors="replace")

    summary_lines, detail_blocks, plain_result = [], [], None
    try:
        data = json.loads(raw)
        if "log" not in data:
            raise ValueError("HAR 형식 아님")
        summary_lines, detail_blocks = analyze_har(data)
    except (json.JSONDecodeError, ValueError):
        plain_result = analyze_plain_text(raw)
        if plain_result is None:
            print("SSV 구분자(0x1e/0x1f)를 찾지 못했습니다. 원문을 그대로 출력합니다.", file=sys.stderr)
            plain_result = raw[:2000]

    report = build_report(src, summary_lines, detail_blocks, plain_result)

    out_path = Path(args.output) if args.output else src.with_name(src.stem + "_analysis.md")
    out_path.write_text(report, encoding="utf-8")
    print(f"리포트 생성 완료: {out_path}")


if __name__ == "__main__":
    main()
