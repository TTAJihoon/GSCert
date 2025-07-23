import json
import pandas as pd
from django.shortcuts import render

def history(request):
    if request.method == 'POST':
        gsnum = request.POST.get('gsnum', '')
        project = request.POST.get('project', '')
        company = request.POST.get('company', '')
        product = request.POST.get('product', '')
        startDate = request.POST.get('start_date', '')
        endDate = request.POST.get('end_date', '')
        comment = request.POST.get('comment', '')
        print(comment, company, product, startDate, endDate, gsnum, project)

        context = {
            'gsnum': gsnum,
            'project': project,
            'company': company,
            'product': product,
            'start_date': startDate,
            'end_date': endDate,
            'comment': comment,
        }
        
        if not gsnum.strip() and not project.strip() and not company.strip() and not product.strip():
            context['response'] = '검색 조건 중 하나 이상을 입력해주세요.'
            return render(request, 'history.html', context)
                
        tables = GS_history(gsnum, project, company, product, startDate, endDate)
        if isinstance(tables, dict):
            tables = [tables]

        tables = list(tables)[::-1]
        context['response_tables'] = tables
        return render(request, 'history.html', context)
               
    # GET 요청 또는 POST 실패 시
    return render(request, 'history.html')

def GS_history(gsnum, project, company, product, startDate, endDate):
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
