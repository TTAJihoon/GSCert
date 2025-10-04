# /your_app/utils/security_extractHTML.py

import json
from bs4 import BeautifulSoup
import bleach

def extract_vulnerability_sections(html_content):
    """
    HTML 콘텐츠에서 보안 취약점 정보를 파싱하여,
    테이블용 데이터와 팝업용 상세 HTML을 반환합니다.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    css_styles = "\n".join(style.prettify() for style in soup.head.find_all('style'))

    # 안정적인 CSS 선택자 사용
    target_divs = soup.select('div.vuln-desc.criticals, div.vuln-desc.highs, div.vuln-desc.mediums')
    results_rows = []

    for div1 in target_divs:
        classes = div1.get('class', [])
        level = "C" if "criticals" in classes else "H" if "highs" in classes else "M"
        
        summary = (div1.find('h2').text.strip()) if div1.find('h2') else "요약 정보 없음"
        description = "\n".join([p.text.strip() for p in div1.find_all('p')])

        div2 = div1.find_next_sibling('div')
        div3 = div2.find_next_sibling('div') if div2 else None
        parent_container = div1.find_parent(class_='container-fluid')
        
        html_snippet = ""
        if all([div1, div2, div3, parent_container]):
            parent_class = ' '.join(parent_container.get('class', []))
            raw_html = f'<div class="{parent_class}">{div1.prettify()}{div2.prettify()}{div3.prettify()}</div>'
            
            # 🛡️ XSS 방지를 위한 HTML 정제
            allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS) | {'div', 'h2', 'h3', 'h4', 'p', 'pre', 'code', 'span', 'ul', 'li', 'ol', 'a', 'svg', 'use', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'input', 'label', 'button', 'style'}
            allowed_attrs = {'*': ['class', 'id', 'style', 'aria-label', 'tabindex', 'role', 'aria-labelledby', 'scope', 'type', 'checked', 'for', 'onclick', 'data-responseid', 'data-button', 'data-panel', 'aria-controls', 'aria-selected', 'aria-expanded', 'aria-hidden']}
            
            html_snippet = bleach.clean(raw_html, tags=allowed_tags, attributes=allowed_attrs, strip=True)

        results_rows.append({
            "id": None, "defect_level": level, "quality_attribute": "보안성",
            "defect_summary": summary, "defect_description": description,
            "invicti_report": summary, "test_env_os": "Windows Server 2019",
            "frequency": "항상", "invicti_analysis": html_snippet,
            "gpt_recommendation": "GPT 분석 버튼을 눌러주세요."
        })

    return {"css": css_styles, "rows": results_rows}
