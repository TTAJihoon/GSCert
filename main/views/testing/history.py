import json
import sqlite3
import pandas as pd
from django.shortcuts import render
from main.request_logging import set_request_log_context

def history(request):
    if request.method == 'POST':
        gsnum = request.POST.get('gsnum', '')
        project = request.POST.get('project', '')
        company = request.POST.get('company', '')
        product = request.POST.get('product', '')
        startDate = request.POST.get('start_date', '')
        endDate = request.POST.get('end_date', '')
        comment = request.POST.get('comment', '')
        search_terms = _search_terms(
            comment=comment,
            company=company,
            product=product,
            start_date=startDate,
            end_date=endDate,
            gsnum=gsnum,
            project=project,
        )
        set_request_log_context(
            request,
            feature="history",
            search=search_terms,
        )

        context = {
            'gsnum': gsnum,
            'project': project,
            'company': company,
            'product': product,
            'start_date': startDate,
            'end_date': endDate,
            'comment': comment,
        }

        tables = GS_history(gsnum, project, company, product, comment, startDate, endDate)
        set_request_log_context(request, result_count=len(tables))
            
        clean_tables = []
        for table in tables:
            clean_table = {
                key.strip().replace(" ", "_").replace("/", "_").replace("\n", "_"): str(value).strip().replace("None", "-")
                for key, value in table.items()
                if not key.startswith('Unnamed')  # 불필요한 Unnamed 컬럼 제거
            }
            clean_tables.append(clean_table)
                
        context['response_tables'] = clean_tables[::-1]
            
        return render(request, 'testing/history.html', context)
               
    # GET 요청 또는 POST 실패 시
    return render(request, 'testing/history.html')


def _search_terms(**terms):
    return {
        key: value.strip()
        for key, value in terms.items()
        if isinstance(value, str) and value.strip()
    }

def GS_history(gsnum='', project='', company='', product='', comment='', startDate='', endDate='', db_path='main/data/reference.db'):
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
    if comment.strip():
        query += " AND 제품설명 LIKE ?"
        params.append(f"%{comment}%")
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
