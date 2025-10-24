from xml.etree import ElementTree as ET

# OMML Namespace (필요에 따라 추가)
ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}

def _parse_omml_element(element):
    """OMML 요소를 재귀적으로 파싱하여 LaTeX 유사 문자열로 변환 (내부 헬퍼)"""
    tag = element.tag.split('}')[-1] # 네임스페이스 제거
    text = "".join(element.itertext()).strip() # 요소 내부의 모든 텍스트

    # 1. 텍스트 요소 (Run)
    if tag == 'r':
        # 실제 텍스트는 t 요소 안에 있음
        t_element = element.find('m:t', ns)
        return t_element.text.strip() if t_element is not None and t_element.text else ""

    # 2. 텍스트 요소 (Text) - <m:t>
    elif tag == 't':
        return text

    # 3. 분수 (Fraction) - <m:f>
    elif tag == 'f':
        num = element.find('m:num/m:e', ns) # numerator / base element
        den = element.find('m:den/m:e', ns) # denominator / base element
        num_str = _parse_omml_element(num) if num is not None else ""
        den_str = _parse_omml_element(den) if den is not None else ""
        # 그룹화가 필요한지 확인 (단일 문자/숫자가 아니면 괄호 추가)
        if len(num_str) > 1 and not num_str.startswith('('): num_str = f"({num_str})"
        if len(den_str) > 1 and not den_str.startswith('('): den_str = f"({den_str})"
        return f"{num_str}/{den_str}"

    # 4. 위 첨자 (Superscript) - <m:sSup>
    elif tag == 'sSup':
        base = element.find('m:e', ns)
        sup = element.find('m:sup/m:e', ns)
        base_str = _parse_omml_element(base) if base is not None else ""
        sup_str = _parse_omml_element(sup) if sup is not None else ""
        if len(base_str) > 1 and not base_str.startswith('('): base_str = f"({base_str})"
        if len(sup_str) > 1 and not sup_str.startswith('('): sup_str = f"({sup_str})"
        return f"{base_str}^{sup_str}"

    # 5. 아래 첨자 (Subscript) - <m:sSub>
    elif tag == 'sSub':
        base = element.find('m:e', ns)
        sub = element.find('m:sub/m:e', ns)
        base_str = _parse_omml_element(base) if base is not None else ""
        sub_str = _parse_omml_element(sub) if sub is not None else ""
        if len(base_str) > 1 and not base_str.startswith('('): base_str = f"({base_str})"
        if len(sub_str) > 1 and not sub_str.startswith('('): sub_str = f"({sub_str})"
        return f"{base_str}_{sub_str}"

    # 6. 위아래 첨자 (Sub-Superscript) - <m:sSubSup>
    elif tag == 'sSubSup':
        base = element.find('m:e', ns)
        sub = element.find('m:sub/m:e', ns)
        sup = element.find('m:sup/m:e', ns)
        base_str = _parse_omml_element(base) if base is not None else ""
        sub_str = _parse_omml_element(sub) if sub is not None else ""
        sup_str = _parse_omml_element(sup) if sup is not None else ""
        if len(base_str) > 1 and not base_str.startswith('('): base_str = f"({base_str})"
        if len(sub_str) > 1 and not sub_str.startswith('('): sub_str = f"({sub_str})"
        if len(sup_str) > 1 and not sup_str.startswith('('): sup_str = f"({sup_str})"
        return f"{base_str}_{sub_str}^{sup_str}"

    # 7. 제곱근 (Radical) - <m:rad>
    elif tag == 'rad':
        base = element.find('m:e', ns)
        deg = element.find('m:deg/m:e', ns) # degree (제곱근 차수)
        base_str = _parse_omml_element(base) if base is not None else ""
        if deg is not None:
             deg_str = _parse_omml_element(deg)
             return f"root({deg_str}, {base_str})"
        else:
             return f"sqrt({base_str})"

    # 8. 구분 기호 (Delimiter) - <m:d> (괄호 등)
    elif tag == 'd':
        # 구분 기호 자체보다는 내부 요소를 파싱
        contents = [_parse_omml_element(el) for el in element.findall('m:e', ns)]
        # 기본적으로 괄호로 묶어줌 (필요시 m:dPr 분석하여 다른 괄호 사용 가능)
        return f"({' '.join(contents)})"

    # 9. 함수 (Function Name) - <m:func> (sin, cos 등) - 단순화
    elif tag == 'func':
        fname = element.find('m:fName/m:e', ns)
        base = element.find('m:e', ns)
        fname_str = _parse_omml_element(fname) if fname is not None else "func"
        base_str = _parse_omml_element(base) if base is not None else ""
        return f"{fname_str}({base_str})"

    # 10. 기본 요소 컨테이너 (Base) - <m:e>
    # <m:e> 자체는 의미가 없고, 자식 요소들을 순서대로 파싱하여 연결
    elif tag == 'e':
        return "".join(_parse_omml_element(child) for child in element) # 모든 자식 순회

    # --- 기타 OMML 태그 (필요에 따라 추가) ---
    # 예: <m:acc> (Accent), <m:bar>, <m:box>, <m:borderBox>
    # <m:groupChr>, <m:limLow>, <m:limUpp>, <m:m> (Matrix)
    # <m:nary> (Sum, Integral), <m:phant>, <m:sPre> (Prescript)

    # 처리되지 않은 태그는 내부 텍스트만 반환 (Fallback)
    else:
        # 자식 요소들을 재귀적으로 파싱 시도
        child_texts = [_parse_omml_element(child) for child in element]
        if child_texts:
            return "".join(child_texts)
        # 자식이 없으면 자신의 텍스트 반환
        return text if text else ""

def parse_omml_to_latex_like(omml_xml_string: str) -> str:
    """
    OMML XML 문자열을 받아 LaTeX 유사 문자열로 변환합니다.
    """
    if not omml_xml_string:
        return ""
    try:
        # 네임스페이스 문제 해결 시도
        if 'xmlns:m' not in omml_xml_string:
             omml_xml_string = omml_xml_string.replace('<m:', '<m_').replace('</m:', '</m_')
             # print(f"DEBUG: Modified OMML: {omml_xml_string[:100]}") # DEBUG
             root = ET.fromstring(omml_xml_string)
             # 루트부터 파싱 시작 (네임스페이스 없이 태그 이름 사용)
             # _parse_omml_element_no_ns 함수 필요 (별도 구현)
             # 여기서는 단순화를 위해 네임스페이스가 있다고 가정하고 진행
             # -> 원본 python-docx XML은 네임스페이스 포함하므로 괜찮을 것임
             return "[OMML Parsing Error: Namespace prefix missing, fallback not implemented]"

        root = ET.fromstring(omml_xml_string)
        # 루트 요소가 oMathPara 또는 oMath일 수 있음, 실제 수식은 그 아래부터 시작
        math_root = root.find('.//m:e', ns) or root # 첫 m:e 또는 루트 자체
        if math_root.tag.endswith('oMathPara') or math_root.tag.endswith('oMath'):
             # 실제 수식 내용 찾기 (보통 m:e 안에 있음)
             base_element = math_root.find('.//m:e', ns)
             if base_element is None: # m:r/m:t 만 있는 단순 수식
                  return "".join(math_root.itertext()).strip()
             math_root = base_element

        return _parse_omml_element(math_root)
    except ET.ParseError as e:
        print(f"  [오류] OMML 파싱 실패: {e} - XML: {omml_xml_string[:100]}...")
        return "[OMML Parse Error]"
    except Exception as e:
        import traceback
        print(f"  [오류] OMML 처리 중 예외 발생: {e}")
        # traceback.print_exc() # 상세 디버깅 필요시
        return "[OMML Processing Error]"
