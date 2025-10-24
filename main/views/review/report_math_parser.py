from xml.etree import ElementTree as ET
import re # 추가

# OMML Namespace (필요에 따라 추가)
# 실제 XML 파싱 시 네임스페이스가 누락될 수 있으므로 유연하게 처리
ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
# 네임스페이스 없이 태그 찾는 helper
def find_math_element(parent, tag_name):
    # 네임스페이스 포함 시도
    element = parent.find(f'm:{tag_name}', ns)
    if element is not None:
        return element
    # 네임스페이스 없이 시도 (XML 구조에 따라 필요할 수 있음)
    # lxml의 경우 namespace prefix 무시 옵션이 더 좋음
    # ElementTree에서는 수동 처리
    return parent.find(tag_name)

def findall_math_elements(parent, tag_name):
    elements = parent.findall(f'm:{tag_name}', ns)
    if elements:
        return elements
    return parent.findall(tag_name)


def _parse_omml_element(element):
    """OMML 요소를 재귀적으로 파싱하여 LaTeX 유사 문자열로 변환 (내부 헬퍼)"""
    if element is None: return "" # None 체크 추가

    tag_match = re.match(r'(\{.*\})?(.*)', element.tag)
    tag = tag_match.group(2) if tag_match else element.tag # 네임스페이스 제거 (더 안전한 방식)

    # 1. 텍스트 요소 (Run 또는 Text)
    if tag == 'r':
        t_element = find_math_element(element, 't')
        # 특수 문자 처리 (예: < > &)
        text = t_element.text.strip() if t_element is not None and t_element.text else ""
        return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    elif tag == 't':
        text = element.text.strip() if element.text else ""
        return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

    # 3. 분수 (Fraction) - <m:f>
    elif tag == 'f':
        num_base = find_math_element(find_math_element(element, 'num'), 'e')
        den_base = find_math_element(find_math_element(element, 'den'), 'e')
        num_str = _parse_omml_element(num_base)
        den_str = _parse_omml_element(den_base)
        # 그룹화 (단일 문자/숫자, 또는 이미 괄호/sqrt/root로 시작하는 경우 제외)
        num_needs_paren = len(num_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', num_str)
        den_needs_paren = len(den_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', den_str)
        if num_needs_paren: num_str = f"({num_str})"
        if den_needs_paren: den_str = f"({den_str})"
        return f"{num_str}/{den_str}"

    # 4. 위 첨자 (Superscript) - <m:sSup>
    elif tag == 'sSup':
        base = find_math_element(element, 'e')
        sup = find_math_element(find_math_element(element, 'sup'), 'e')
        base_str = _parse_omml_element(base)
        sup_str = _parse_omml_element(sup)
        base_needs_paren = len(base_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', base_str)
        sup_needs_paren = len(sup_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', sup_str)
        if base_needs_paren: base_str = f"({base_str})"
        if sup_needs_paren: sup_str = f"({sup_str})"
        return f"{base_str}^{sup_str}"

    # 5. 아래 첨자 (Subscript) - <m:sSub>
    elif tag == 'sSub':
        base = find_math_element(element, 'e')
        sub = find_math_element(find_math_element(element, 'sub'), 'e')
        base_str = _parse_omml_element(base)
        sub_str = _parse_omml_element(sub)
        base_needs_paren = len(base_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', base_str)
        sub_needs_paren = len(sub_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', sub_str)
        if base_needs_paren: base_str = f"({base_str})"
        if sub_needs_paren: sub_str = f"({sub_str})"
        return f"{base_str}_{sub_str}"

    # 6. 위아래 첨자 (Sub-Superscript) - <m:sSubSup>
    elif tag == 'sSubSup':
        base = find_math_element(element, 'e')
        sub = find_math_element(find_math_element(element, 'sub'), 'e')
        sup = find_math_element(find_math_element(element, 'sup'), 'e')
        base_str = _parse_omml_element(base)
        sub_str = _parse_omml_element(sub)
        sup_str = _parse_omml_element(sup)
        base_needs_paren = len(base_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', base_str)
        sub_needs_paren = len(sub_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', sub_str)
        if sub_needs_paren: sub_str = f"({sub_str})"
        sup_needs_paren = len(sup_str) > 1 and not re.match(r'^[a-zA-Z0-9]$|^[\(\[\{].*[\)\]\}]$|^(sqrt|root)\(.*\)$', sup_str)
        if sup_needs_paren: sup_str = f"({sup_str})"
        if base_needs_paren: base_str = f"({base_str})"
        return f"{base_str}_{sub_str}^{sup_str}"

    # 7. 제곱근 (Radical) - <m:rad>
    elif tag == 'rad':
        base = find_math_element(element, 'e')
        deg = find_math_element(find_math_element(element, 'deg'), 'e')
        base_str = _parse_omml_element(base)
        if deg is not None:
             deg_str = _parse_omml_element(deg)
             return f"root({deg_str}, {base_str})"
        else:
             return f"sqrt({base_str})"

    # 8. 구분 기호 (Delimiter) - <m:d> (괄호 등)
    elif tag == 'd':
        contents = [_parse_omml_element(el) for el in findall_math_elements(element, 'e')]
        # 괄호 종류 분석 (선택적) - m:dPr -> m:begChr, m:endChr
        # 여기서는 기본 괄호 사용
        return f"({' '.join(contents)})"

    # 9. 함수 이름 (Function Name) - <m:func>
    elif tag == 'func':
        fname = find_math_element(find_math_element(element, 'fName'), 'e')
        base = find_math_element(element, 'e') # 함수 인자 부분
        fname_str = _parse_omml_element(fname) if fname is not None else "func"
        base_str = _parse_omml_element(base) if base is not None else ""
        return f"{fname_str}({base_str})"

    # 10. N-ary 연산자 (Sum, Integral 등) - <m:nary> (기본 처리)
    elif tag == 'nary':
        sub = find_math_element(find_math_element(element, 'sub'), 'e') # 아래 첨자 (시작)
        sup = find_math_element(find_math_element(element, 'sup'), 'e') # 위 첨자 (끝)
        base = find_math_element(element, 'e') # 기본 식
        char_elem = find_math_element(element, 'chr') # 연산 기호 (∑, ∫ 등)
        op_char = char_elem.get('{http://schemas.openxmlformats.org/officeDocument/2006/math}val') if char_elem is not None else '?'

        sub_str = f"_{_parse_omml_element(sub)}" if sub is not None else ""
        sup_str = f"^{_parse_omml_element(sup)}" if sup is not None else ""
        base_str = _parse_omml_element(base) if base is not None else ""
        # LaTeX 유사 형식 단순화
        return f"{op_char}{sub_str}{sup_str} ({base_str})"


    # 11. 기본 요소 컨테이너 (Base) - <m:e>
    elif tag == 'e':
        # <m:e>는 자식 요소들을 순서대로 연결
        return "".join(_parse_omml_element(child) for child in element)

    # 처리되지 않은 태그는 자식 요소 파싱 결과 또는 내부 텍스트 반환
    else:
        child_texts = [_parse_omml_element(child) for child in element]
        if child_texts:
            return "".join(child_texts)
        # 자식이 없으면 자신의 텍스트 반환 (이미 위에서 처리됨, 방어 코드)
        text = "".join(element.itertext()).strip()
        return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


def parse_omml_to_latex_like(omml_xml_string: str) -> str:
    """
    OMML XML 문자열 (<m:oMathPara> 또는 <m:oMath> 포함)을 받아
    LaTeX 유사 문자열로 변환합니다.
    """
    if not omml_xml_string: return ""

    try:
        # 네임스페이스 자동 처리 시도 (lxml이 설치되어 있으면 더 좋음)
        # ElementTree 기본 파서는 네임스페이스 URI를 태그에 포함시킴
        # 루트 태그에서 네임스페이스 정보 추출 시도 (선택적)
        # root = ET.fromstring(omml_xml_string)
        # print(f"Root tag: {root.tag}") # DEBUG

        # XML 문자열에서 네임스페이스 선언 제거 (간단한 처리 방식)
        cleaned_xml = re.sub(r'xmlns(:\w+)?="[^"]+"', '', omml_xml_string, count=1)
        # 접두사 'm:' 제거 (더 간단하게 파싱하기 위해)
        cleaned_xml = cleaned_xml.replace('<m:', '<').replace('</m:', '</')

        root = ET.fromstring(cleaned_xml)

        # 실제 수식 시작 요소 찾기 (oMathPara > oMath > e)
        math_root = root.find('.//e') or root.find('.//oMath') or root

        if math_root is not None:
             # 루트 요소 자체는 건너뛰고 자식부터 파싱 시작
             # oMath, oMathPara는 컨테이너일 뿐
             if math_root.tag in ['oMath', 'oMathPara']:
                  # 첫번째 자식 'e'를 찾거나 없으면 그냥 자식들 연결
                  first_e = math_root.find('.//e')
                  if first_e is not None:
                      return _parse_omml_element(first_e)
                  else: # 단순 텍스트만 있는 경우
                      return "".join(math_root.itertext()).strip()
             else: # 이미 'e' 또는 다른 요소
                 return _parse_omml_element(math_root)
        else:
             return "[OMML Root Not Found]" # 파싱 실패

    except ET.ParseError as e:
        print(f"  [오류] OMML 파싱 실패: {e} - XML: {omml_xml_string[:100]}...")
        return "[OMML Parse Error]"
    except Exception as e:
        import traceback
        print(f"  [오류] OMML 처리 중 예외 발생: {e}")
        # traceback.print_exc() # 상세 디버깅
        return "[OMML Processing Error]"
