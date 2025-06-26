from main.utils.reload_reference import reload_reference_dataframe, getREF

def GS_history(company, product):
    REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        reload_reference_dataframe()
        REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        # 그래도 None이면 로딩 실패한 상태
        raise ValueError("REFERENCE_DF is still None. CSV 파일이 로딩되지 않았습니다.")
        
    df = REFERENCE_DF.copy()

    if company.strip():
        df = df[df['회사명'].fillna('').str.contains(company, case=False)]

    if product.strip():
        df = df[df['제품'].fillna('').str.contains(product, case=False)]

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
