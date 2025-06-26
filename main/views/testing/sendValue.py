import json
import pandas as pd
from django.shortcuts import render
from .history import GS_history
#from .chatbot import run_ollama_with_reference

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
            if not company.strip() and not product.strip():
                context['response'] = '회사명 또는 제품명 중 하나 이상을 입력해주세요.'
                return render(request, 'index.html', context)
                
            tables = GS_history(company, product)
            if isinstance(tables, dict):
                tables = [tables]

            tables = list(tables)[::-1]
            context['response_tables'] = tables
            return render(request, 'index.html', context)

        elif selected == 'similar':
#            try:
#                result_str = run_ollama_with_reference(startDate, endDate, comment)
#                print("[DEBUG] LLM 응답 원문:", result_str[:500])
#                result_json = json.loads(result_str)
#            except Exception as e:
#                print("[ERROR] 유사도 검색 오류:", e)
#                result_json = []
#                context['response'] = "유사도 검색 중 오류 발생 또는 응답 파싱 실패"
                
                context['response_tables'] = result_json
                return render(request, 'index.html', context)
                
    # GET 요청 또는 POST 실패 시
    return render(request, 'index.html')
