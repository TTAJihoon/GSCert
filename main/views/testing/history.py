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

def GS_history(gsnum='', project='', company='', product='', startDate='', endDate='', db_path='main/data/reference.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 컬럼명을 사용해서 결과를 가져올 수 있게 설정
    cursor = conn.cursor()

    # 기본 쿼리 생성
    query = "SELECT * FROM sw_data WHERE 1=1"
    params = []

    # 조건을 확인하여 쿼리에 추가
    if gsnum.strip():
        query += " AND 인증번호 LIKE ?"
        params.append(f"%{gsnum}%")
    if project.strip():
        query += " AND 시험번호 LIKE ?"
        params.append(f"%{project}%")
    if company.strip():
        query += " AND 회사명 LIKE ?"
        params.append(f"%{company}%")
    if product.strip():
        query += " AND 제품 LIKE ?"
        params.append(f"%{product}%")
    if startDate.strip():
        query += " AND 시작일자 >= ?"
        params.append(startDate)
    if endDate.strip():
        query += " AND 종료일자 <= ?"
        params.append(endDate)

    # 쿼리 실행
    cursor.execute(query, params)
    rows = cursor.fetchall()

    # 결과를 딕셔너리 형태로 변환
    result = [dict(row) for row in rows]

    conn.close()

    return result
