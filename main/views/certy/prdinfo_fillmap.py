def build_fill_map(obj1: dict, obj2: dict, obj3: dict):
    """
    - 시트 "제품 정보 요청": 1번+2번 매핑
    - 시트 "결함정보": 3번 매핑
    (한 셀 내 2줄은 '\n')
    """

    prod_sheet = {
        # (1번 과정: 합의서)
        "D5": obj1.get("시험신청번호", ""),
        "N5": obj1.get("성적서 구분", ""),
        "B5": "\n".join([obj1.get("국문명", ""), obj1.get("영문명", "")]).strip("\n"),
        "B7": obj1.get("사업자등록번호", ""),
        "C7": obj1.get("법인등록번호", ""),
        "D7": obj1.get("대표자", ""),
        "E7": obj1.get("대표 전화번호", ""),
        "F7": obj1.get("대표자 E-Mail", ""),
        "G7": obj1.get("주 소", ""),
        "H7": "\n".join([obj1.get("담당자-성 명", ""), obj1.get("담당자-부서/직급", "")]).strip("\n"),
        "I7": obj1.get("담당자-Mobile", ""),
        "J7": obj1.get("담당자-FAX번호", ""),
        "K7": obj1.get("담당자-E- Mail", ""),
        "L7": "\n".join([obj1.get("제조자", ""), obj1.get("제조국가", "")]).strip("\n"),
        "M7": obj1.get("홈페이지", ""),
        "C5": "\n".join([obj1.get("국문명:", ""), obj1.get("영문명:", "")]).strip("\n"),

        # (2번 과정: 성적서/결과서)
        "K5": "\n".join(obj2.get("시험기간", []) or []),
        "F5": obj2.get("개요 및 특성(설명)", "") or "",
        "G5": "\n".join(obj2.get("개요 및 특성(주요 기능)", []) or []),
        "H5": obj2.get("소요일수 합계", 0),
    }

    # 3번 → “결함정보”
    defect_sheet = {
        "B4": obj3.get("결함차수", 0),
        "C4": obj3.get("적합성", {}).get("수정전", 0),
        "D4": obj3.get("효율성", {}).get("수정전", 0),
        "E4": obj3.get("호환성", {}).get("수정전", 0),
        "F4": obj3.get("사용성", {}).get("수정전", 0),
        "G4": obj3.get("신뢰성", {}).get("수정전", 0),
        "H4": obj3.get("보안성", {}).get("수정전", 0),
        "I4": obj3.get("유지보수성", {}).get("수정전", 0),
        "J4": obj3.get("이식성", {}).get("수정전", 0),
        "K4": obj3.get("요구사항", {}).get("수정전", 0),
        "L4": obj3.get("High", {}).get("수정전", 0),
        "M4": obj3.get("Medium", {}).get("수정전", 0),
        "N4": obj3.get("Low", {}).get("수정전", 0),
    }

    return {
        "제품 정보 요청": prod_sheet,
        "결함정보": defect_sheet,
    }
