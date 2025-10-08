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
    h4_tag = vuln_block.find('h4', string=re.compile(text, re.I))
    if h4_tag:
        next_sibling = h4_tag.find_next_sibling()
        if next_sibling and next_sibling.find('li'):
            return next_sibling.find('li').text.strip()
    return ''

def get_variables_default(vuln_block):
    return {}

def get_variables_for_urls(vuln_block):
    urls = vuln_block.select('.vuln-url div')
    url_texts = [re.sub(r'^\d+\.\d+\.\s*', '', url.text.strip()) for url in urls]
    return {'url': '\n'.join(url_texts)}

def get_variables_for_weak_ciphers(vuln_block):
    selector = "li[data-description*='지원되는 약한 암호 목록']"
    weak_ciphers = [li.text.strip() for li in vuln_block.select(selector)]
    return {'weak': '\n'.join(weak_ciphers)}

def get_variables_for_out_of_date(vuln_block):
    v1 = _find_h4_sibling_text(vuln_block, 'Overall Latest Version')
    v2 = _find_h4_sibling_text(vuln_block, '확인된 버전')
    
    o_text = ''
    out_of_date_tag = vuln_block.find(string=re.compile(r'Out-of-date Version', re.I))
    if out_of_date_tag:
        match = re.search(r'\((.*?)\)', out_of_date_tag)
        if match:
            o_text = match.group(1)
            
    return {'v1': v1, 'v2': v2, 'o': o_text}

# --- 3. A열 번호와 추출 함수 매핑 ---
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

    # [수정] 각 취약점 설명 블록('.vuln-desc')을 직접 순회하도록 변경
    target_divs = soup.select('div.vuln-desc.criticals, div.vuln-desc.highs, div.vuln-desc.mediums')
    
    for vuln_desc_div in target_divs:
        # [수정] 팝업용 HTML 조각을 만들기 위해 현재 블록과 다음 두 형제 요소를 찾음
        vuln_details_div = vuln_desc_div.find_next_sibling('div')
        remediation_div = vuln_details_div.find_next_sibling('div') if vuln_details_div else None
        
        # `vuln_block`을 현재 취약점의 유효 범위로 사용
        # `vuln_block`은 변수 추출과 팝업 내용 생성에 모두 사용됨
        vuln_block = BeautifulSoup(str(vuln_desc_div) + str(vuln_details_div) + str(remediation_div), 'html.parser')

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
            # [수정] 변수 추출 함수에 현재 취약점 범위(vuln_block)를 전달
            variables = handler(vuln_block)

            for key, value in variables.items():
                template_summary = template_summary.replace(f'{{{key}}}', value)
                template_description = template_description.replace(f'{{{key}}}', value)
            
            defect_summary = template_summary
            defect_description = template_description
        
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
            # [수정] `invicti_analysis`에 현재 취약점의 HTML 조각만 저장
            "invicti_analysis": vuln_block.prettify(),
            "gpt_recommendation": "GPT 분석 버튼을 눌러주세요.",
        }
        results_rows.append(row_data)

    return {"css": "", "rows": results_rows}
