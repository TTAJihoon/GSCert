# main_script.py
import json
import re
import pdfplumber
from docx import Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# --- 다른 파일에서 함수 임포트 ---
from report_table_parser import parse_table
from report_math_parser import parse_omml_to_latex_like
# ---------------------------------

# --- 파일 경로 설정 ---
DOCX_PATH = "C://GSCert//myproject//GS-B-25-0094 시험성적서 v1.0.docx"
PDF_PATH = "C://GSCert//myproject//GS-B-25-0094 시험성적서 v1.0.pdf"
# ---------------------

def normalize_text(text: str):
    """텍스트의 모든 종류 공백(유니코드 포함)을 단일 스페이스로 정규화합니다."""
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

# --- 1. 라벨 식별 함수 (동일) ---
RE_VER_STRING = re.compile(r'^\s*v\d+\.\d+')
RE_NUM_LABEL = re.compile(r'^\s*(\d+(\.\d+)*)[\.\s]\s*(.*)')
RE_TAG_LABEL = re.compile(r'^\s*<\s*([^>]+?)\s*>\s*(.*)')

def get_label_info(text: str):
    clean_text = text.strip()
    if not clean_text or RE_VER_STRING.match(clean_text): return None
    if clean_text.startswith("·"): return None

    match = None; depth = 1; label_prefix = ""; full_label_text = ""
    match_num = RE_NUM_LABEL.match(clean_text)
    if match_num:
        label_prefix = match_num.group(1).strip(); full_label_text = match_num.group(3).strip()
        depth = label_prefix.count('.') + 1
        if not full_label_text and clean_text.endswith('.'):
             if clean_text == label_prefix + '.': label_prefix += "."
        match = match_num
    match_tag = RE_TAG_LABEL.match(clean_text)
    if match_tag:
        label_prefix = f"<{match_tag.group(1).strip()}>"; full_label_text = match_tag.group(2).strip()
        depth = 1; match = match_tag
    if not match: return None

    final_label = ""; final_rest = ""
    if ':' in full_label_text:
        parts = full_label_text.split(':', 1)
        final_label = f"{label_prefix} {parts[0].strip()}".strip(); final_rest = parts[1].strip()
    else:
        final_label = f"{label_prefix} {full_label_text}".strip(); final_rest = ""
    if final_label.endswith('.'):
         original_suffix = clean_text.replace(label_prefix, '').strip()
         if original_suffix == '.': final_label = label_prefix
    if not full_label_text.strip() and label_prefix:
        if label_prefix.endswith('.'): final_label = label_prefix
    if re.match(r'^\d+\.$', final_label): return None
    return final_label, final_rest, depth

# --- 2. PDF 분석 함수 (7% 경계 수정) ---
def analyze_pdf(pdf_path: str):
    """
    [7% 경계 수정] PDF를 분석하고 extract_words로 첫 줄 앵커를 추출/정규화합니다.
    """
    print(f"--- 1. PDF 분석 시작: {pdf_path} ---")
    pdf_data = {}; total_pages = 0
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages); print(f"총 페이지 수: {total_pages}")
        for i, page in enumerate(pdf.pages):
            page_num = page.page_number; height = page.height
            header_boundary = height * 0.07 # 7% 수정
            footer_boundary = height * 0.93 # 7% 수정
            header_lines = []; footer_lines = []

            words = page.extract_words(keep_blank_chars=True, y_tolerance=3, x_tolerance=1)
            content_words = [w for w in words if header_boundary <= w['top'] and w['bottom'] <= footer_boundary]
            anchor_text = None
            if content_words:
                first_word = min(content_words, key=lambda w: w['top']); first_line_top = first_word['top']
                first_line_words = sorted([w for w in content_words if abs(w['top'] - first_line_top) < 3], key=lambda w: w['x0'])
                anchor_raw_text = "".join(w['text'] for w in first_line_words)
                anchor_text = normalize_text(anchor_raw_text)

            all_lines = page.extract_text_lines(return_chars=False)
            if all_lines:
                 for line in all_lines:
                     text = line['text'];
                     if not text.strip(): continue
                     page_match = re.search(r'페이지\s*:\s*\(\s*(\d+)\s*\)\s*(?:/\s*\(총?\s*(\d+)\s*\))?', text)
                     if page_match and line['bottom'] > footer_boundary:
                          current_pg=page_match.group(1); total_pg_num=page_match.group(2) or total_pages
                          footer_lines.append(f"페이지: ({current_pg})/({total_pg_num})")
                     elif line['top'] < header_boundary: header_lines.append(text.strip())
                     elif line['bottom'] > footer_boundary:
                         clean_line = text.strip()
                         if "페이지" not in clean_line and clean_line not in footer_lines: footer_lines.append(clean_line)

            footer_lines = sorted(list(set(footer_lines)))
            pdf_data[page_num] = {"header": sorted(list(set(header_lines))), "footer": footer_lines, "anchor": anchor_text}
            if i < 7 or i > total_pages - 3: print(f"  [Page {page_num}] 앵커: '{anchor_text}' / 푸터 샘플: {footer_lines[:2]}")
    print("--- 1. PDF 분석 완료 ---")
    return total_pages, pdf_data

# --- 3. DOCX 1차 파싱 (math_parser, table_parser 호출) ---
def parse_docx_flat(docx_path: str, pdf_page_data: dict):
    """
    [수정] math_parser와 table_parser 함수를 호출합니다.
    """
    print(f"--- 2. DOCX 1차 파싱 시작: {docx_path} ---")
    anchors = {};
    for p_num, data in pdf_page_data.items():
        anchor = data.get('anchor');
        if anchor and anchor not in anchors: anchors[anchor] = p_num

    doc = Document(docx_path)
    page_flat_content = {p_num: [] for p_num in pdf_page_data.keys()}
    current_page_num = 1; is_page_1_table_processed = False

    for element in doc.element.body:
        block = None; is_anchor_found = False; current_element_anchor_text = None

        if isinstance(element, CT_P):
            para = Paragraph(element, doc)
            current_element_anchor_text = normalize_text(para.text)

            if current_element_anchor_text and current_element_anchor_text in anchors:
                new_page_num = anchors[current_element_anchor_text]
                if new_page_num != current_page_num:
                    print(f"  [페이지 전환] P: '{current_element_anchor_text}' -> Page {new_page_num}")
                    current_page_num = new_page_num
                is_anchor_found = True

            # --- 수식 처리 ---
            # 단락 XML 내부에 <m:oMathPara> 또는 <m:oMath> 태그가 있는지 확인
            omml_tags = element.xpath('.//m:oMathPara | .//m:oMath', namespaces={'m': ns['m']})
            if omml_tags:
                 print(f"  [수식 발견] Page {current_page_num}, 내용: {para.text[:30]}...")
                 # 첫 번째 수식 태그의 XML 문자열 추출
                 omml_xml_string = ET.tostring(omml_tags[0], encoding='unicode')
                 # math_parser 호출
                 math_text = parse_omml_to_latex_like(omml_xml_string)
                 block = {"type": "sen", "sen": math_text}
                 # TODO: 수식 앞뒤 텍스트 처리 필요 시 추가 로직
            elif para.text.strip(): # 수식이 아니고 빈 단락도 아니면 기존 로직
                label_info = get_label_info(para.text.strip())
                if label_info:
                    label, rest, depth = label_info
                    block = {"type": "label", "label": label, "content": [], "depth": depth}
                    if rest: block["content"].append({"sen": rest})
                else:
                    block = {"type": "sen", "sen": para.text.strip()}

        elif isinstance(element, CT_Tbl):
            table = Table(element, doc)
            if table.rows:
                first_row_cells = table.rows[0].cells
                for cell in first_row_cells:
                    cell_text_normalized = normalize_text(cell.text)
                    if cell_text_normalized and cell_text_normalized in anchors:
                        new_page_num = anchors[cell_text_normalized]
                        if new_page_num != current_page_num:
                            print(f"  [페이지 전환] T: '{cell_text_normalized}' -> Page {new_page_num}")
                            current_page_num = new_page_num
                        is_anchor_found = True; current_element_anchor_text = cell_text_normalized
                        break

            if table.rows:
               # --- table_parser 호출 ---
               block = parse_table(table)
               block["type"] = "table"

        if block: page_flat_content[current_page_num].append(block)

        # --- 1페이지 특수 처리 (동일) ---
        if (current_page_num == 1 and block and block.get("type") == "table" and
            current_element_anchor_text == "시험성적서" and not is_page_1_table_processed):
            print("  [Page 1] 테이블 내부 라벨/sen 추출 중...")
            is_page_1_table_processed = True
            try:
                tbl_element = element; tr = tbl_element.tr_lst[2]; tc = tr.tc_lst[1]
                page_1_stack = []
                for p in tc.xpath('.//w:p', namespaces=qn.nsmap): # Use qn.nsmap
                    para = Paragraph(p, table); para_text = para.text.strip()
                    if not para_text: continue
                    label_info = get_label_info(para_text)
                    if label_info:
                        label, rest, depth = label_info
                        new_block = {"type": "label", "label": label, "content": [], "depth": depth}
                        if rest: new_block["content"].append({"sen": rest})
                        page_flat_content[current_page_num].append(new_block)
                        page_1_stack = [(new_block, depth)]
                    elif para_text.startswith("·") and page_1_stack:
                        last_label_block_ref, _ = page_1_stack[-1]
                        if "content" not in last_label_block_ref: last_label_block_ref["content"] = []
                        last_label_block_ref["content"].append({"sen": para_text})
            except (IndexError, AttributeError) as e:
                print(f"  [경고] 1페이지 테이블 구조 분석 실패: {e}.")
                pass
    print("--- 2. DOCX 1차 파싱 완료 ---")
    return page_flat_content


# --- 4. 2차 파싱 (중첩 구조 생성) 함수 (동일) ---
def build_nested_content(flat_blocks: list):
    nested_content = []; stack = []
    for block in flat_blocks:
        block_type = block.get("type")
        if "type" in block: block.pop("type")
        elif "sen" in block: block_type = "sen"
        elif "table" in block: block_type = "table"
        else: continue
        if block_type == "label":
            depth = block.pop("depth", 1)
            while stack and stack[-1][1] >= depth: stack.pop()
            if not stack: nested_content.append(block)
            else:
                parent_label_block, _ = stack[-1]
                if "content" not in parent_label_block: parent_label_block["content"] = []
                parent_label_block["content"].append(block)
            stack.append((block, depth))
        elif block_type in ["sen", "table"]:
             current_block = block #if block_type else {"sen": block["sen"]}
             if not stack: nested_content.append(current_block)
             else:
                 parent_label_block, _ = stack[-1]
                 if "content" not in parent_label_block: parent_label_block["content"] = []
                 parent_label_block["content"].append(current_block)
    return nested_content

# --- 5. 커스텀 JSON 저장 함수 (동일) ---
def save_as_custom_json(data, filename: str):
    print(f"--- 4. 커스텀 JSON 포맷팅 및 저장 시작: {filename} ---")
    try:
        pretty_json_str = json.dumps(data, indent=2, ensure_ascii=False)
    except TypeError as e:
        print(f"  [오류] JSON 직렬화 실패: {e}");
        with open(filename, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  [경고] 기본 포맷으로 저장됨."); return

    table_block_regex = re.compile(r'"table":\s*(\[.*?\])', re.DOTALL)
    def compress_table_match(match):
        table_str = match.group(1)
        try:
            table_list = json.loads(table_str)
            compressed_str = json.dumps(table_list, ensure_ascii=False, separators=(',', ':')) # 공백 최소화
            return f'"table": {compressed_str}'
        except json.JSONDecodeError as e:
            print(f"  [경고] 테이블 JSON 압축 실패 (파싱 오류): {e} - {table_str[:100]}...")
            return match.group(0)
    final_json_str = table_block_regex.sub(compress_table_match, pretty_json_str)
    with open(filename, 'w', encoding='utf-8') as f: f.write(final_json_str)


# --- 6. 메인 실행 함수 (동일) ---
def main():
    try: total_pages, pdf_page_data = analyze_pdf(PDF_PATH)
    except Exception as e: print(f"PDF 분석 오류: {e}"); return
    try: all_pages_flat_content = parse_docx_flat(DOCX_PATH, pdf_page_data)
    except Exception as e: import traceback; print(f"DOCX 파싱 오류: {e}"); traceback.print_exc(); return

    print("--- 3. 중첩 구조 생성 시작 ---"); final_pages_list = []
    for page_num in sorted(pdf_page_data.keys()):
        flat_blocks = all_pages_flat_content.get(page_num, [])
        if page_num == 3: # 목차
            content = []
            for block in flat_blocks:
                 block_type = block.get("type")
                 if block_type == "label": content.append({"sen": block["label"]})
                 elif block_type == "sen": content.append({"sen": block["sen"]})
        else: content = build_nested_content(flat_blocks)
        page_obj = {"page": page_num, "header": pdf_page_data.get(page_num, {}).get("header", []),
                    "footer": pdf_page_data.get(page_num, {}).get("footer", []), "content": content}
        final_pages_list.append(page_obj)
    print("--- 3. 중첩 구조 생성 완료 ---")

    final_json = {"v": "0.4", "total_pages": total_pages, "pages": final_pages_list}
    output_filename = "output.json"
    try: save_as_custom_json(final_json, output_filename); print(f"\n🎉 작업 완료! 결과가 {output_filename} 에 저장되었습니다.")
    except Exception as e: print(f"최종 JSON 저장 오류: {e}")

if __name__ == "__main__":
    main()
