import re
from main.utils.reload_reference import reload_reference_dataframe, getREF

def extract_all_names(name: str) -> list:
    """회사명에서 현재/과거 이름을 모두 추출"""
    name = name.strip()
    if '(구:' in name:
        m = re.match(r"(.*?)\(구:\s*(.*?)\)", name)
        if m:
            return [
                m.group(1).strip().lower(),  # 현재 이름
                m.group(2).strip().lower()   # 과거 이름
            ]
    return [name.lower()]

def GS_history(company, product):
    REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        reload_reference_dataframe()
        REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        raise ValueError("REFERENCE_DF is still None. CSV 파일이 로딩되지 않았습니다.")
    
    df = REFERENCE_DF.copy()
    df.columns = df.columns.str.strip()

    # ✅ 회사명 필터링 (검색어가 어떤 이름 일부라도 포함되면 매칭)
    if company.strip():
        search_name = company.strip().lower()
        df["회사명_키워드목록"] = df["회사명"].fillna("").apply(extract_all_names)

        df = df[df["회사명_키워드목록"].apply(
            lambda names: any(search_name in name for name in names)
        )]

    # ✅ 제품명 필터링 (부분 포함 그대로 유지)
    if product.strip():
        product = product.strip()
        df = df[df['제품'].fillna('').str.contains(product, case=False)]

    # ✅ 결과 구성
    results = []
    for _, row in df.iterrows():
        results.append({
            'a1': row.get('일련번호', ''),
            'a2': row.get('인증번호', ''),
            'a3': row.get('인증일자', ''),
            'a4': row.get('회사명', ''),
            'a5': row.get('제품', ''),
            'a6': row.get('등급', ''),
            'a7': row.get('시험번호', ''),
            'a8': row.get('S/W분류', ''),
            'a9': row.get('제품 설명', ''),
            'a10': row.get('총WD', ''),
            'a11': row.get('재계약', ''),
            'a12': row.get('특이사항', ''),
            'a13': row.get('시작날짜/\n종료날짜', ''),
            'a14': row.get('시험원', '')
        })

    return results
