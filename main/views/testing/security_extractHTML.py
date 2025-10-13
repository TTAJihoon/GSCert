import json
import re
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List
import pandas as pd
import bleach
from bleach.css_sanitizer import CSSSanitizer
from fuzzywuzzy import fuzz

# --- 1. 엑셀 파일 로드 ---
try:
    df_security_map = pd.read_excel("main/data/security.xlsx", sheet_name="Sheet1")
except FileNotFoundError:
    print("오류: security.xlsx 파일을 찾을 수 없습니다. py 파일과 동일한 경로에 위치시켜주세요.")
    df_security_map = pd.DataFrame()

# --- 2. 변수 추출 함수 정의 ---
def _get_vuln_block_from_desc(vuln_desc_div):
    vuln_elements = [vuln_desc_div]
    for sibling in vuln_desc_div.find_next_siblings():
        if sibling.name == 'div' and 'vuln-desc' in sibling.get('class', []):
            break
        vuln_elements.append(sibling)
    block_html = "".join(str(el) for el in vuln_elements)
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
    url_texts = []
    for url in urls:
        text = url.text.strip()
        text = re.sub(r'^\d+\.\d+\.\s*', '', text)
        if text.endswith('확정됨'):
            text = text[:-len('확정됨')].strip()

        if text:
            url_texts.append(text)
            
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
    return {'v1': v1, 'v2': v2}

# --- 3. 핸들러 매핑 ---
VARIABLE_HANDLERS = {
    1: get_variables_for_out_of_date, 2: get_variables_for_out_of_date,
    9: get_variables_for_urls, 10: get_variables_for_urls, 12: get_variables_for_urls, 14: get_variables_for_urls, 16: get_variables_for_urls, 17: get_variables_for_urls, 18: get_variables_for_urls, 19: get_variables_for_urls,
    11: get_variables_for_weak_ciphers, 22: get_variables_for_weak_ciphers,
    3: get_variables_default, 4: get_variables_default, 5: get_variables_default, 6: get_variables_default, 7: get_variables_default, 8: get_variables_default, 13: get_variables_default, 15: get_variables_default, 20: get_variables_default, 21: get_variables_default, 23: get_variables_default, 24: get_variables_default, 25: get_variables_default, 26: get_variables_default, 27: get_variables_default, 28: get_variables_default, 29: get_variables_default,
}

def _clean_text(el) -> str:
    return "" if el is None else el.get_text("\n", strip=True)

def _vd_parse_table(detail_div) -> Optional[Dict[str, Any]]:
    table = detail_div.find('table')
    if not table:
        return None
    first_tr = table.find('tr')
    if not first_tr:
        return None
    headers = [th.get_text(strip=True) for th in first_tr.find_all(['th','td'])]

    # 열 key 매핑 (사람이/LLM이 이해 쉬운 columns/rows 구조)
    mapping: List[tuple] = []
    for h in headers:
        h_norm = h.replace(" ", "").lower()
        if ('메서드' in h) or ('method' in h_norm): mapping.append(("method", h))
        elif ('매개변수형식' in h) or ('형식' in h) or ('type' in h_norm): mapping.append(("type", h))
        elif ('매개변수' in h) or ('parameter' in h_norm) or ('param' in h_norm): mapping.append(("param", h))
        elif ('값' in h) or ('value' in h_norm): mapping.append(("value", h))
        else: mapping.append((f"col_{len(mapping)}", h))

    rows = []
    for tr in table.find_all('tr')[1:]:
        cells = [td.get_text("\n", strip=True) for td in tr.find_all(['td','th'])]
        if len(cells) < len(mapping):
            cells += ['']*(len(mapping)-len(cells))
        row_obj = {}
        for (key, _label), val in zip(mapping, cells[:len(mapping)]):
            row_obj[key] = val
        rows.append(row_obj)

    columns = [{"key": k, "label": lbl} for (k, lbl) in mapping]
    return {"columns": columns, "rows": rows}

def _vd_find_proof_url(detail_div) -> Optional[str]:
    lab = detail_div.find(string=re.compile(r'증명\s*URL|Proof\s*URL', re.I))
    if lab and lab.parent:
        a = lab.parent.find('a', href=True)
        if a and a.get('href'):
            return a['href']
        a2 = lab.find_next('a', href=True)
        if a2 and a2.get('href'):
            return a2['href']
    a = detail_div.find('a', href=True)
    return a['href'] if a else None

def _vd_extract_pre_text(container, selector: str) -> Optional[str]:
    el = container.select_one(selector)
    if not el:
        return None
    pre = el.find('pre')
    if not pre:
        return _clean_text(el)
    code = pre.find('code')
    return code.get_text("\n", strip=False) if code else pre.get_text("\n", strip=False)

def extract_first_vuln_detail_json_from_html(html: str) -> Optional[Dict[str, Any]]:
    """
    원본 html에서 '첫 번째' vuln-detail만 JSON으로 추출.
    ※ 기존 soup를 건드리지 않도록 '별도 soup'에서만 읽음
    우선순위 컨테이너: div.vulns.highs → div.vulns → 문서 전체
    """
    s = BeautifulSoup(html, 'html.parser')
    container = s.select_one('div.vulns.highs') or s.select_one('div.vulns')
    if container:
        detail = container.select_one('div.vuln-detail')
    else:
        detail = s.select_one('div.vuln-detail')
    if not detail:
        return None

    return {
        "table": _vd_parse_table(detail),
        "url": _vd_find_proof_url(detail),
        "request": _vd_extract_pre_text(detail, '.vuln-tab.vuln-req1-tab'),
        "response": _vd_extract_pre_text(detail, '.vuln-tab.vuln-resp1-tab'),
    }

# --- 4. 메인 추출 함수 ---
def extract_vulnerability_sections(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    css_styles = "\n".join(style.prettify() for style in soup.head.find_all('style'))
    allowed_css_properties = ['color', 'background-color', 'width', 'height', 'font-size', 'font-weight', 'text-align', 'padding', 'margin', 'border', 'border-left-width', 'display', 'float', 'word-break']
    css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_css_properties)
    results_rows = []
    
    # 유사도 점수 임계값 (이 값을 조절하여 매칭 민감도를 변경할 수 있습니다)
    SIMILARITY_THRESHOLD = 85
    
    target_divs = soup.select('div.vuln-desc.criticals, div.vuln-desc.highs, div.vuln-desc.mediums')
    
    for vuln_desc_div in target_divs:
        h2_tag = vuln_desc_div.find('h2')
        if not h2_tag: continue
        
        h2_text = h2_tag.text.strip()
        cleaned_title = re.sub(r'^\d+\.\s*', '', h2_text)

        matched_row = None
        if not df_security_map.empty:
            best_match_score = 0
            best_match_row = None
            
            # FuzzyWuzzy를 사용하여 가장 유사한 행을 찾는 로직
            for index, row in df_security_map.iterrows():
                invicti_item = str(row['invicti 결함 리포트 항목']).strip()
                if not invicti_item:
                    continue
                
                # 단어 순서, 개수에 상관없이 유사도 점수 계산
                score = fuzz.token_set_ratio(cleaned_title, invicti_item)
                
                if score > best_match_score:
                    best_match_score = score
                    best_match_row = row
            
            # 가장 높은 점수가 임계값을 넘을 경우에만 매칭된 것으로 인정
            if best_match_score >= SIMILARITY_THRESHOLD:
                matched_row = best_match_row
        
        defect_summary = h2_text
        defect_description = "\n".join([p.text.strip() for p in vuln_desc_div.find_all('p')])

        if matched_row is not None:
            template_summary = str(matched_row['TTA 결함 리포트 결함 요약'])
            template_description = str(matched_row['결함 내용'])
            
            o_text = ''
            match = re.search(r'\((.*?)\)', h2_text)
            if match:
                o_text = match.group(1).strip()
            
            # 다른 변수들은 핸들러를 통해 추출
            handler_id = matched_row['번호']
            handler = VARIABLE_HANDLERS.get(handler_id, get_variables_default)
            other_variables = handler(vuln_desc_div)
            
            # 모든 변수를 합치고 템플릿에 적용
            all_variables = {'o': o_text, **other_variables}
            for key, value in all_variables.items():
                if value:
                    template_summary = template_summary.replace(f'{{{key}}}', value)
                    template_description = template_description.replace(f'{{{key}}}', value)
            
            defect_summary = template_summary
            defect_description = template_description
        
        vuln_elements_for_snippet = [vuln_desc_div]
        for sibling in vuln_desc_div.find_next_siblings():
            if sibling.name == 'div' and 'vuln-desc' in sibling.get('class', []):
                break
            vuln_elements_for_snippet.append(sibling)

        parent_container = vuln_desc_div.find_parent(class_='container-fluid')
        html_snippet = ""
        if parent_container:
            parent_class = ' '.join(parent_container.get('class', []))
            inner_html = "".join(el.prettify() for el in vuln_elements_for_snippet)
            raw_html = f'<div class="{parent_class}">{inner_html}</div>'
            allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS) | {'div', 'h2', 'h3', 'h4', 'p', 'pre', 'code', 'span', 'ul', 'li', 'ol', 'a', 'svg', 'use', 'path', 'g', 'circle', 'rect', 'polygon', 'defs', 'style', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'input', 'label', 'button'}
            allowed_attrs = {'*': ['class', 'id', 'style', 'aria-label', 'tabindex', 'role', 'aria-labelledby', 'scope', 'type', 'checked', 'for', 'data-responseid', 'data-button', 'data-panel', 'aria-controls', 'aria-selected', 'aria-expanded', 'aria-hidden', 'viewbox', 'xmlns', 'points', 'cx', 'cy', 'r', 'd', 'fill', 'transform', 'x', 'y', 'width', 'height', 'rx', 'ry', 'xlink:href', 'x1', 'y1', 'x2', 'y2', 'stroke', 'stroke-width']}
            html_snippet = bleach.clean(raw_html, tags=allowed_tags, attributes=allowed_attrs, css_sanitizer=css_sanitizer, strip=True)

        level_class = vuln_desc_div.get('class', [])
        defect_level = 'H' if any(c in level_class for c in ['criticals', 'highs']) else 'M' if 'mediums' in level_class else ''

        row_data = {
            "id": None, "test_env_os": "시험환경\n모든 OS",
            "defect_summary": defect_summary, "defect_level": defect_level,
            "frequency": "A", "quality_attribute": "보안성",
            "defect_description": defect_description, "invicti_report": h2_text,
            "invicti_analysis": html_snippet, "gpt_recommendation": "GPT 분석 버튼을 눌러주세요.",
        }
        results_rows.append(row_data)

        first_vuln_detail_json = extract_first_vuln_detail_json_from_html(html_content)

    return {
        "css": css,
        "rows": rows,
        "first_vuln_detail_json": first_vuln_detail_json
    }
