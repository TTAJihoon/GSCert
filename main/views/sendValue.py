import os
import pandas as pd
from django.conf import settings
from django.shortcuts import render
from .chatbot  import run_ollama_model  # 내부 모듈에서 함수 가져오기

# 1. reference.csv 파일을 메모리에 로딩 (초기 1회)
REFERENCE_PATH = os.path.join(settings.BASE_DIR, 'main', 'data', 'reference.csv')
REFERENCE_DF = pd.read_csv(REFERENCE_PATH, skiprows=3)

def GS_history(q1):
    # 회사명 열 기준으로 부분 일치 검색 (NaN 방지)
    matches = REFERENCE_DF[REFERENCE_DF['회사명'].fillna('').str.contains(q1, case=False)]

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

def search_history(request):
    if request.method == 'POST':
        q1 = request.POST.get('company', '')  # ← 회사명
        tables = GS_history(q1)
        return render(request, 'index.html', {'response_tables': tables})
    return render(request, 'index.html')
    
def chat_gpt(request):
    if request.method == 'POST':
        q1 = request.POST.get('company', '')
        q2 = request.POST.get('product', '')
        q3 = request.POST.get('startDate', '')
        q4 = request.POST.get('endDate', '')
        q5 = request.POST.get('comment', '')

        # 내부 모듈 함수 호출
        result = run_ollama_model(q1, q2, q3, q4, q5)

       # 결과를 index.html에 출력
        return render(request, 'index.html', {'response': result})
        
    return render(request, 'index.html')
