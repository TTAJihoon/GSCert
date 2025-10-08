import json
import re
from bs4 import BeautifulSoup
import pandas as pd

# --- 1. 엑셀 파일 로드 및 전역 변수 설정 ---
try:
    df_security_map = pd.read_excel("security.xlsx", sheet_name="Sheet1")
except FileNotFoundError:
    print("오류: security.xlsx 파일을 찾을 수 없습니다. py 파일과 동일한 경로에 위치시켜주세요.")
    df_security_map = pd.DataFrame()

# --- 2. 변수 추출을 위한 개별 함수 정의 ---

def _find_h4_sibling_text(vuln_block, text):
    """h4 태그를 찾고, 그 바로 다음 형제 요소의 텍스트를 반환하는 헬퍼 함수"""
    h4_tag = vuln_block.find('h4', string=re.compile(text, re.I))
    if h4_tag:
        next_sibling = h4_tag.find_next_sibling()
        if next_sibling and next_sibling.find('li'):
            return next_sibling.find('li').text.strip()
    return ''

def get_variables_default(vuln_block):
    """변수가 필요 없는 경우, 빈 딕셔너리를 반환합니다."""
    return {}

def get_variables_for_urls(vuln_block):
    """{url} 변수를 추출합니다."""
    urls = vuln_block.select('.vuln-url div')
    url_texts = [re.sub(r'^\d+\.\d+\.\s*', '', url.text.strip()) for url in urls]
    return {'url': '\n'.join(url_texts)}

def get_variables_for_weak_ciphers(vuln_block):
    """{weak} 변수를 추출합니다."""
    selector = "li[data-description*='지원되는 약한 암호 목록']"
    weak_ciphers = [li.text.strip() for li in vuln_block.select(selector)]
    return {'weak': '\n'.join(weak_ciphers)}

def get_variables_for_out_of_date(vuln_block):
    """{v1}, {v2}, {o} 변수를 추출합니다."""
    v1 = _find_h4_sibling_text(vuln_block, 'Overall Latest Version')
    v2 = _find_h4_sibling_text(vuln_block, '확인된 버전')
    
    o_text = ''
    out_of_date_tag = vuln_block.find(string=re.compile(r'Out-of-date Version', re.I))
    if out_of_date_tag:
        match = re.search(r'\((.*?)\)', out_of_date_tag)
        if match:
            o_text = match.group(1)
            
    return {'v1': v1, 'v2': v2, 'o': o_text}

# --- 3. A열 번호와 추출 함수를 매핑하는 딕셔너리 ---
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
    results_rows = []

    # [수정] criticals, highs, mediums 등급만 선택하도록 명시
    vuln_names = soup.select('.vuln-name')
    
    for block in vuln_names:
        vuln_desc = block.select_one('div.vuln-desc.criticals, div.vuln-desc.highs, div.vuln-desc.mediums')
        if not vuln_desc:
            continue

        h2_tag = vuln_desc.find('h2')
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
        defect_description = "\n".join([p.text.strip() for p in vuln_desc.find_all('p')])

        if matched_row is not None:
            template_summary = str(matched_row['TTA 결함 리포트 결함 요약'])
            template_description = str(matched_row['결함 내용'])
            
            handler_id = matched_row['번호']
            handler = VARIABLE_HANDLERS.get(handler_id, get_variables_default)
            variables = handler(block)

            for key, value in variables.items():
                template_summary = template_summary.replace(f'{{{key}}}', value)
                template_description = template_description.replace(f'{{{key}}}', value)
            
            defect_summary = template_summary
            defect_description = template_description
        
        # [수정] '결함정도' 최종 판별 로직
        level_class = vuln_desc.get('class', [])
        if any(c in level_class for c in ['criticals', 'highs']):
            defect_level = 'H'
        elif 'mediums' in level_class:
            defect_level = 'M'
        else:
            defect_level = '' # 해당되지 않는 경우는 없지만 안전을 위해 기본값 설정

        # [수정] 요청사항에 맞게 최종 row 데이터 구성
        row_data = {
            "id": None,
            "test_env_os": "시험환경\n모든 OS",
            "defect_summary": defect_summary,
            "defect_level": defect_level,
            "frequency": "A",
            "quality_attribute": "보안성",
            "defect_description": defect_description,
            "invicti_report": h2_text,
            "invicti_analysis": block.prettify(),
            "gpt_recommendation": "GPT 분석 버튼을 눌러주세요.",
        }
        results_rows.append(row_data)

    return {"css": "", "rows": results_rows}
