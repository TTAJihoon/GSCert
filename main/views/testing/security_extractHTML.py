import json
from bs4 import BeautifulSoup

def extract_vulnerability_sections(html_content):
    """
    HTML 콘텐츠에서 'vuln-desc' 클래스를 포함하는 div와 관련 코드 블록을 추출합니다.

    Args:
        html_content (str): 분석할 전체 HTML 문자열입니다.

    Returns:
        str: 추출된 코드 블록을 포함하는 JSON 형식의 문자열입니다.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # CSS 스타일 추출
    # <head> 태그 안의 모든 <style> 태그 내용을 합칩니다.
    css_styles = "\n".join(style.prettify() for style in soup.head.find_all('style'))

    # 'vuln-desc criticals', 'vuln-desc highs', 'vuln-desc mediums' 클래스를 가진 div 찾기
    target_classes = ['vuln-desc criticals', 'vuln-desc highs', 'vuln-desc mediums']
    # class_ 속성에 공백이 포함된 여러 클래스를 직접 전달할 수 없으므로, 함수를 사용하여 찾습니다.
    def class_selector(tag):
        return tag.name == 'div' and ' '.join(tag.get('class', [])) in target_classes
        
    target_divs = soup.find_all(class_selector)

    # 결과를 저장할 딕셔너리
    extracted_data = {}

    for i, div1 in enumerate(target_divs):
        # 다음 두 형제 div 찾기
        div2 = div1.find_next_sibling('div')
        if not div2: continue
        div3 = div2.find_next_sibling('div')
        if not div3: continue

        # 스타일 적용을 위한 상위 div의 클래스 정보 찾기
        # 이 경우, 스타일 컨텍스트를 제공하는 가장 가까운 공통 상위 컨테이너를 찾습니다.
        parent_container = div1.find_parent(class_='container-fluid')
        if not parent_container: continue
        
        parent_class = ' '.join(parent_container.get('class', []))

        # 추출된 div들을 감싸서 완전한 HTML 구조 만들기
        # 상위 div 구조와 CSS를 포함하여 렌더링 시 스타일이 올바르게 적용되도록 합니다.
        full_html_snippet = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    {css_styles}
</head>
<body>
    <div class="{parent_class}">
        {div1.prettify()}
        {div2.prettify()}
        {div3.prettify()}
    </div>
</body>
</html>
        """
        
        # JSON 객체에 추가
        extracted_data[str(i + 1)] = full_html_snippet

    # 딕셔너리를 JSON 형식의 문자열로 변환 (한글 깨짐 방지 및 보기 좋게 출력)
    return json.dumps(extracted_data, indent=2, ensure_ascii=False)

# 업로드된 파일의 전체 내용을 변수에 저장
# 실제 환경에서는 파일을 읽어오는 로직이 필요합니다.
# 여기서는 제공된 'fullContent'를 사용합니다.
file_content = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml" lang="en"><meta charset="UTF-8" /><meta http-equiv="X-UA-Compatible" content="IE=edge" /><meta name="viewport" content="width=device-width,initial-scale=1" /><head><title>Invicti Standard &#xC5D0; &#xB300;&#xD55C; &#xB137;&#xC2A4;&#xD30C;&#xCEE4; &#xC2A4;&#xCE94;&#xBCF4;&#xACE0;&#xC11C;
... (업로드된 HTML 파일의 전체 내용) ...
"""

# 함수를 호출하여 결과 JSON 생성
result_json = extract_vulnerability_sections(fullContent)

# 디버깅용으로 최종 JSON 출력
print(result_json)
