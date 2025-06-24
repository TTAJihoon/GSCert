import json
import pandas as pd
from django.shortcuts import render
from .chatbot import run_ollama_with_reference, reload_reference_context
from main.utils.constants import REFERENCE_PATH

# 전역 DataFrame
REFERENCE_DF = None

def reload_reference_dataframe():
    global REFERENCE_DF
    try:
        REFERENCE_DF = pd.read_csv(REFERENCE_PATH, skiprows=3)
        print("[INFO] REFERENCE_DF reloaded.")
    except Exception as e:
        print("[ERROR] DataFrame reload 실패:", e)

# 초기 1회 로딩
reload_reference_dataframe()

def search_history(request):
    if request.method == 'POST':
        selected = request.POST.get('selectType')  # ← 라디오 버튼 값
        company = request.POST.get('company', '')
        product = request.POST.get('product', '')
        startDate = request.POST.get('startDate', '')
        endDate = request.POST.get('endDate', '')
        comment = request.POST.get('comment', '')

        context = {
            'selected_type': selected,
            'company': company,
            'product': product,
            'start_date': startDate,
            'end_date': endDate,
            'comment': comment,
        }
        
        if selected == 'history':
            if not company.strip():
                context['response'] = '회사명을 입력해주세요.'
                return render(request, 'index.html', context)

            tables = GS_history(company)
            context['response_tables'] = tables
            return render(request, 'index.html', context)

        elif selected == 'similar':
            try:
                result_str = run_ollama_with_reference(startDate, endDate, comment)
                print("[DEBUG] LLM 응답 원문:", result_str[:500])
                result_json = json.loads(result_str)
            except Exception as e:
                print("[ERROR] 유사도 검색 오류:", e)
                result_json = []
                context['response'] = "유사도 검색 중 오류 발생 또는 응답 파싱 실패"
                
                context['response_tables'] = result_json
                return render(request, 'index.html', context)
                
    # GET 요청 또는 POST 실패 시
    return render(request, 'index.html')
    
def GS_history(company):
    if not isinstance(company, str) or not company.strip():
        return []  # 또는 raise ValidationError("회사명을 입력하세요.")

    matches = REFERENCE_DF[
        REFERENCE_DF['회사명'].fillna('').str.contains(company, case=False)
    ]

    results = []
    for _, row in matches.iterrows():
        result = {
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
            'a13': row.get('시작날짜/종료날짜', ''),
            'a14': row.get('시험원', '')
        }
        results.append(result)
    return results
    
def reload_reference_view(request):
    reload_reference_context()
    reload_reference_dataframe()
    return render(request, 'index.html', {
        'response': 'reference.csv 파일이 다시 로드되었습니다.'
    })
