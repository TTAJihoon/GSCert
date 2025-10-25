# report_math_parser.py (lxml 기반 재설계)
from lxml import etree
import re

# OMML Namespace (lxml용)
ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

# 그룹화 필요 여부 체크 함수 (개선)
def needs_paren(content: str) -> bool:
    content = content.strip()
    # 단일 문자/숫자, 이미 괄호/루트/함수/첨자 형태, 연산기호 제외
    # 복잡한 표현식은 괄호로 묶는 것을 기본으로 함
    if not content: return False
    # 단순 식별자 (글자/숫자/_ 만)
    if re.fullmatch(r'[a-zA-Z0-9_]+', content): return False
    # 이미 괄호로 시작하거나 끝나는 경우
    if content.startswith(('(', '[', '{')) and content.endswith((')', ']', '}')): return False
    # 함수, 루트 형태
    if re.match(r'^(sqrt|root)\(.*\)$|^\w+\(.*\)$', content): return False
    # 첨자 형태 (a_b, a^b, a_b^c) - 단순화된 체크
    if re.match(r'.*[_^].+', content) and ' ' not in content: return False
    # 그 외에는 괄호 추가 (예: a+b, a/b)
    return True

def parse_single_child(element, child_xpath):
    """지정된 XPath로 자식 하나를 찾아 파싱"""
    child = element.xpath(child_xpath, namespaces=ns)
    return _parse_lxml_element(child[0]) if child else ""

def parse_all_children(element, child_xpath='./*'):
    """지정된 XPath로 모든 자식을 찾아 파싱하고 결과를 join"""
    children = element.xpath(child_xpath, namespaces=ns)
    return "".join(_parse_lxml_element(child) for child in children)


def _parse_lxml_element(element):
    """lxml 요소를 재귀적으로 파싱하여 LaTeX 유사 문자열로 변환 (재설계)"""
    if element is None: return ""

    tag = etree.QName(element).localname
    # print(f"Processing tag: {tag}") # DEBUG

    # 1. 리프 노드: 텍스트 런 (<w:r> 또는 <m:r>)
    if tag == 'r':
        text = "".join(element.xpath('.//w:t/text() | .//m:t/text()', namespaces=ns)).strip()
        text = re.sub(r'\s+', ' ', text).strip()
        return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    # 2. 리프 노드: 텍스트 (<m:t>)
    elif tag == 't':
        text = element.text.strip() if element.text else ""
        text = re.sub(r'\s+', ' ', text).strip()
        return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

    # --- 구조 정의 노드 처리 ---

    # 3. 분수 (Fraction) - <m:f>
    elif tag == 'f':
        # 수정: num/den 요소를 찾고, 그 *안의 모든 자식*을 파싱
        num_content = parse_all_children(element, './m:num/*')
        den_content = parse_all_children(element, './m:den/*')
        if needs_paren(num_content): num_content = f"({num_content})"
        if needs_paren(den_content): den_content = f"({den_content})"
        return f"{num_content}/{den_content}"

    # 4. 위 첨자 (Superscript) - <m:sSup>
    elif tag == 'sSup':
        base_content = parse_all_children(element, './m:e/*')
        sup_content = parse_all_children(element, './m:sup/*')
        if needs_paren(base_content): base_content = f"({base_content})"
        if needs_paren(sup_content): sup_content = f"({sup_content})"
        return f"{base_content}^{sup_content}"

    # 5. 아래 첨자 (Subscript) - <m:sSub>
    elif tag == 'sSub':
        base_content = parse_all_children(element, './m:e/*')
        sub_content = parse_all_children(element, './m:sub/*')
        if needs_paren(base_content): base_content = f"({base_content})"
        if needs_paren(sub_content): sub_content = f"({sub_content})"
        return f"{base_content}_{sub_content}"

    # 6. 위아래 첨자 (Sub-Superscript) - <m:sSubSup>
    elif tag == 'sSubSup':
        base_content = parse_all_children(element, './m:e/*')
        sub_content = parse_all_children(element, './m:sub/*')
        sup_content = parse_all_children(element, './m:sup/*')
        if needs_paren(base_content): base_content = f"({base_content})"
        if needs_paren(sub_content): sub_content = f"({sub_content})"
        if needs_paren(sup_content): sup_content = f"({sup_content})"
        return f"{base_content}_{sub_content}^{sup_content}"

    # 7. 제곱근 (Radical) - <m:rad>
    elif tag == 'rad':
        base_content = parse_all_children(element, './m:e/*')
        deg_content = parse_all_children(element, './m:deg/*')
        if deg_content:
             return f"root({deg_content}, {base_content})"
        else:
             return f"sqrt({base_content})"

    # 8. 구분 기호 (Delimiter) - <m:d> (괄호 등)
    elif tag == 'd':
        contents = parse_all_children(element, './m:e/*')
        dPr = element.xpath('./m:dPr', namespaces=ns)
        open_char = "("; close_char = ")"
        if dPr:
             begChr_elems = dPr[0].xpath('./m:begChr', namespaces=ns)
             endChr_elems = dPr[0].xpath('./m:endChr', namespaces=ns)
             if begChr_elems and qn('m:val') in begChr_elems[0].attrib: open_char = begChr_elems[0].get(qn('m:val'))
             if endChr_elems and qn('m:val') in endChr_elems[0].attrib: close_char = endChr_elems[0].get(qn('m:val'))
        return f"{open_char}{contents}{close_char}"

    # 9. 함수 (Function Name) - <m:func>
    elif tag == 'func':
        fname_content = parse_all_children(element, './m:fName/*')
        base_content = parse_all_children(element, './m:e/*')
        fname_str = fname_content if fname_content else "func"
        return f"{fname_str}({base_content})"

    # 10. N-ary 연산자 (Sum, Integral 등) - <m:nary>
    elif tag == 'nary':
        sub_content = parse_all_children(element, './m:sub/*')
        sup_content = parse_all_children(element, './m:sup/*')
        base_content = parse_all_children(element, './m:e/*')
        char_elem = element.xpath('./m:chr', namespaces=ns)
        op_char = char_elem[0].get(qn('m:val')) if char_elem and qn('m:val') in char_elem[0].attrib else '?'
        sub_str = f"_{sub_content}" if sub_content else ""
        sup_str = f"^{sup_content}" if sup_content else ""
        # 괄호 추가 개선
        if needs_paren(base_content): base_str_paren = f"({base_content})"
        elif base_content: base_str_paren = f" {base_content}" # 구분 위해 공백 추가
        else: base_str_paren = ""
        return f"{op_char}{sub_str}{sup_str}{base_str_paren}"

    # --- 일반 컨테이너 노드 처리 ---
    # `e`, `oMath`, `oMathPara` 및 구조 태그의 내부 컨테이너 (`num`, `den`, `sub`, `sup` 등)
    # 이 태그들은 단순히 자식들의 결과를 순서대로 합쳐서 반환
    elif tag in ['e', 'oMath', 'oMathPara', 'num', 'den', 'sup', 'sub', 'fName', 'deg', 'argPr']:
        return "".join(_parse_lxml_element(child) for child in element.xpath('./*', namespaces=ns))

    # --- Fallback ---
    # 위에서 처리되지 않은 모든 다른 태그들
    else:
        # print(f"  [Fallback] Unknown Tag {tag} - Joining children") # DEBUG
        # 자식이 있으면 자식 결과를 합치고, 없으면 텍스트 반환
        children = element.xpath('./*', namespaces=ns)
        if children:
            return "".join(_parse_lxml_element(child) for child in children)
        else:
            text = "".join(element.itertext()).strip()
            text = re.sub(r'\s+', ' ', text).strip()
            return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


def parse_omml_to_latex_like(omml_xml_string: str) -> str:
    """
    OMML XML 문자열 (<m:oMathPara> 또는 <m:oMath> 포함)을 받아
    lxml을 사용하여 LaTeX 유사 문자열로 변환합니다. (재설계)
    """
    if not omml_xml_string: return ""
    # global _debug_indent # 디버깅 시 주석 해제
    # _debug_indent = 0   # 디버깅 시 주석 해제

    try:
        if omml_xml_string.startswith('\ufeff'): omml_xml_string = omml_xml_string[1:]
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        root = etree.fromstring(omml_xml_string.encode('utf-8'), parser=parser)
        result = _parse_lxml_element(root)
        final_result = re.sub(r'\s+', ' ', result).strip()
        # print(f"DEBUG MATH: Final Parsed Math: '{final_result}'") # DEBUG
        return final_result

    except etree.XMLSyntaxError as e:
        print(f"  [오류] OMML 파싱 실패 (lxml): {e} - XML: {omml_xml_string[:100]}...")
        try: # Fallback 시도
             parser_fb = etree.XMLParser(recover=True, encoding='utf-8')
             root_fb = etree.fromstring(omml_xml_string.encode('utf-8'), parser=parser_fb)
             text_content = "".join(root_fb.itertext()).strip()
             return text_content if text_content else "[OMML Parse Error]"
        except: return "[OMML Parse Error]"
    except Exception as e:
        import traceback
        print(f"  [오류] OMML 처리 중 예외 발생 (lxml): {e}")
        # traceback.print_exc()
        return "[OMML Processing Error]"
