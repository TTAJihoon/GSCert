import re
from datetime import datetime
from main.utils.reload_reference import reload_reference_dataframe, getREF

def extract_all_names(name: str) -> list:
    """
    회사명에서 현재/과거 이름을 모두 추출 (예: 'B(구: A)' → ['B', 'A'])
    """
    name = name.strip()
    if '(구:' in name:
        m = re.match(r"(.*?)\(구:\s*(.*?)\)", name)
        if m:
            return [
                m.group(1).strip().lower(),  # 현재 이름
                m.group(2).strip().lower()   # 과거 이름
            ]
    return [name.lower()]

def is_within_date_range(doc_start, doc_end, query_start, query_end):
    try:
        doc_start = datetime.fromisoformat(doc_start.strip()) if doc_start else None
        doc_end = datetime.fromisoformat(doc_end.strip()) if doc_end else None
        query_start = datetime.fromisoformat(query_start.strip())
        query_end = datetime.fromisoformat(query_end.strip())

        if doc_start and query_start <= doc_start <= query_end:
            return True
        if doc_end and query_start <= doc_end <= query_end:
            return True
        if doc_start and doc_end and doc_start <= query_start and doc_end >= query_end:
            return True
    except:
        return False
    return False

def parse_korean_date_range(text: str):
    try:
        print(text,"-------------------")
        text = re.sub(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", r"\1.\2.\3", text)
        text = text.replace(" ", "").replace("~", " ~ ")
        dates = re.findall(r"\d{4}\.\d{1,2}\.\d{1,2}", text)
        print(date,"-------------------")
        if len(dates) == 2:
            start = datetime.strptime(dates[0], "%Y.%m.%d").date().isoformat()
            end = datetime.strptime(dates[1], "%Y.%m.%d").date().isoformat()
            print(start,end,"-------------------")
            return start, end
    except:
        pass
    return None, None

def GS_history(company, product, query_start=None, query_end=None):
    REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        reload_reference_dataframe()
        REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        raise ValueError("REFERENCE_DF is still None. CSV 파일이 로딩되지 않았습니다.")

    df = REFERENCE_DF.copy()
    df.columns = df.columns.str.strip()

    if company.strip():
        search = company.strip().lower()
        df["회사명_키워드목록"] = df["회사명"].fillna("").apply(extract_all_names)

        all_related_names = set()
        for names in df["회사명_키워드목록"]:
            if any(search in name for name in names):
                all_related_names.update(names)

        df = df[df["회사명_키워드목록"].apply(
            lambda names: any(name in all_related_names for name in names)
        )]

    if product.strip():
        product = product.strip()
        df = df[df['제품'].fillna('').str.contains(product, case=False)]

    results = []
    for _, row in df.iterrows():
        raw_date = row.get('시작날짜/\n종료날짜', '')
        start_date, end_date = parse_korean_date_range(raw_date)

        if query_start and query_end:
            if not is_within_date_range(start_date, end_date, query_start, query_end):
                continue  # 날짜 범위가 맞지 않으면 넘어가기

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
            'a13': raw_date,
            'a14': row.get('시험원', '')
        })

    return results
