import json
import re
from bs4 import BeautifulSoup
import pandas as pd
import bleach
from bleach.css_sanitizer import CSSSanitizer

# --- 1. 엑셀 파일 로드 ---
try:
    df_security_map = pd.read_excel("main/data/security.xlsx", sheet_name="Sheet1")
except FileNotFoundError:
    print("오류: security.xlsx 파일을 찾을 수 없습니다. py 파일과 동일한 경로에 위치시켜주세요.")
    df_security_map = pd.DataFrame()

# --- 2. 변수 추출 함수 정의 ---

def _get_vuln_block_from_desc(vuln_desc_div):
    """vuln-desc div를 기준으로 관련된 div 3개를 묶어 BeautifulSoup 객체로 반환"""
    details_div = vuln_desc_div.find_next_sibling('div')
    remediation_div = details_div.find_next_sibling('div') if details_div else None
    
    # 세 개의 div를 문자열로 합쳐서 하나의 컨텍스트로 만듦
    # 이렇게 하면 이 블록 내에서만 검색을 수행할 수 있음
    block_html = str(vuln_desc_div) + str(details_div) + str(remediation_div)
    return BeautifulSoup(block_html, 'html.parser')

def _find_h4_sibling_text(vuln_block, text):
    h4_tag = vuln_block.find('h4', string=re.compile(text, re.I))
    if h4_tag:
        next_sibling = h4_tag.find_next_sibling()
        if next_sibling and next_sibling.find('li'):
            return next_sibling.find('li').text.strip()
    return ''

def get_variables_default(vuln_desc_div):
    return {}

def get_variables_for_urls(vuln_desc_div):
    block = _get_vuln_block_from_desc(vuln_desc_div)
    urls = block.select('.vuln-url div')
    url_texts = [re.sub(r'^\d+\.\d+\.\s*', '', url.text.strip()) for url in urls]
    return {'url': '\n'.join(url_texts)}

def get_variables_for_weak_ciphers(vuln_desc_div):
    block = _get_vuln_block_from_desc(vuln_desc_div)
    selector = "li[data-description*='지원되는 약한 암호 목록']"
    weak_ciphers = [li.text.strip() for li in block.select(selector)]
    return {'weak': '\n'.join(weak_ciphers)}

def get_variables_for_out_of_date(vuln_desc_div):
    block = _get_vuln_block_from_desc(vuln_desc_div)
    v1 = _find_h4_sibling_text(block, 'Overall Latest Version')
    v2 = _find_h4_sibling_text(block, '확인된 버전')
    
    o_text = ''
    out_of_date_tag = block.find(string=re.compile(r'Out-of-date Version', re.I))
    if out_of_date_tag:
        match = re.search(r'\((.*?)\)', out_of_date_tag)
        if match:
            o_text = match.group(1)
            
    return {'v1': v1, 'v2': v2, 'o': o_text}

# --- 3. 핸들러 매핑 ---
VARIABLE_HANDLERS = {
    1: get_variables_for_out_of_date, 2: get_variables_for_out_of_date,
    9: get_variables_for_urls, 10: get_variables_for_urls, 12: get_variables_for_urls,
    14: get_variables_for_urls, 16: get_variables_for_urls, 17: get_variables_for_urls,
    18: get_variables_for_urls, 19: get_variables_for_urls,
    11: get_variables_for_weak_ciphers, 22: get_variables_for_weak_ciphers,
    3: get_variables_default, 4: get_variables_default, 5: get_variables_default,
    6: get_variables_default, 7: get_variables_default, 8: get_variables_default,
    13: get_variables_default, 15: get_variables_default, 20: get_variables_default,
    21: get_variables_default, 23: get_variables_default, 24: get_variables_default,
    25: get_variables_default, 26: get_variables_default, 27: get_variables_default,
    28: get_variables_default, 29: get_variables_default,
}

# --- 4. 메인 추출 함수 ---
def extract_vulnerability_sections(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    allowed_css_properties = [
        'color', 'background-color', 'width', 'height', 'font-size', 
        'font-weight', 'text-align', 'padding', 'margin', 'border',
        'border-left-width', 'display', 'float', 'word-break'
    ]
    # bleach 내장 CSSSanitizer를 사용합니다.
    css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_css_properties)
    
    results_rows = []
    target_divs = soup.select('div.vuln-desc.criticals, div.vuln-desc.highs, div.vuln-desc.mediums')
    
    for vuln_desc_div in target_divs:
        h2_tag = vuln_desc_div.find('h2')
        if not h2_tag:
            continue
        
        h2_text = h2_tag.text.strip()
        cleaned_title = re.sub(r'^\d+\.\s*', '', h2_text)

        matched_row = None
        if not df_security_map.empty:
            for index, row in df_security_map.iterrows():
                invicti_item = str(row['invicti 결함 리포트 항목'])
                if invicti_item and invicti_item in cleaned_title:
                    matched_row = row
                    break
        
        defect_summary = h2_text
        defect_description = "\n".join([p.text.strip() for p in vuln_desc_div.find_all('p')])

        if matched_row is not None:
            template_summary = str(matched_row['TTA 결함 리포트 결함 요약'])
            template_description = str(matched_row['결함 내용'])
            
            handler_id = matched_row['번호']
            handler = VARIABLE_HANDLERS.get(handler_id, get_variables_default)
            variables = handler(vuln_desc_div)

            for key, value in variables.items():
                if value: # 값이 있는 경우에만 치환
                    template_summary = template_summary.replace(f'{{{key}}}', value)
                    template_description = template_description.replace(f'{{{key}}}', value)
            
            defect_summary = template_summary
            defect_description = template_description

        # --- 팝업용 HTML 생성 (정상 동작했던 코드 기준) ---
        div2 = vuln_desc_div.find_next_sibling('div')
        div3 = div2.find_next_sibling('div') if div2 else None
        parent_container = vuln_desc_div.find_parent(class_='container-fluid')
        
        html_snippet = ""
        if all([vuln_desc_div, div2, div3, parent_container]):
            parent_class = ' '.join(parent_container.get('class', []))
            raw_html = f'<div class="{parent_class}">{vuln_desc_div.prettify()}{div2.prettify()}{div3.prettify()}</div>'
            
            allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS) | {'div', 'h2', 'h3', 'h4', 'p', 'pre', 'code', 'span', 'ul', 'li', 'ol', 'a', 'svg', 'use', 'path', 'g', 'circle', 'rect', 'polygon', 'defs', 'style', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'input', 'label', 'button'}
            allowed_attrs = {'*': ['class', 'id', 'style', 'aria-label', 'tabindex', 'role', 'aria-labelledby', 'scope', 'type', 'checked', 'for', 'onclick', 'data-responseid', 'data-button', 'data-panel', 'aria-controls', 'aria-selected', 'aria-expanded', 'aria-hidden', 'viewbox', 'xmlns', 'points', 'cx', 'cy', 'r', 'd', 'fill', 'transform', 'x', 'y', 'width', 'height', 'rx', 'ry', 'xlink:href', 'x1', 'y1', 'x2', 'y2', 'stroke', 'stroke-width']}
            
            html_snippet = bleach.clean(raw_html, tags=allowed_tags, attributes=allowed_attrs, css_sanitizer=css_sanitizer, strip=True)

        level_class = vuln_desc_div.get('class', [])
        defect_level = 'H' if any(c in level_class for c in ['criticals', 'highs']) else 'M' if 'mediums' in level_class else ''

        row_data = {
            "id": None,
            "test_env_os": "시험환경\n모든 OS",
            "defect_summary": defect_summary,
            "defect_level": defect_level,
            "frequency": "A",
            "quality_attribute": "보안성",
            "defect_description": defect_description,
            "invicti_report": h2_text,
            "invicti_analysis": html_snippet, # 정상 생성된 HTML 조각으로 저장
            "gpt_recommendation": "GPT 분석 버튼을 눌러주세요.",
        }
        results_rows.append(row_data)

    # css_styles는 이제 사용되지 않으므로 빈 문자열로 반환
    return {"css": "", "rows": results_rows}
