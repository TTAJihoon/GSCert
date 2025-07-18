import json
import pandas as pd
from django.shortcuts import render
from .history import GS_history
from .similar_GPT import run_openai_GPT

def search_history(request):
    if request.method == 'POST':
        selected = request.POST.get('selectType')  # ← 라디오 버튼 값
        company = request.POST.get('company', '')
        product = request.POST.get('product', '')
        startDate = request.POST.get('start_date', '')
        endDate = request.POST.get('end_date', '')
        comment = request.POST.get('comment', '')
        print(comment, company, product, startDate, endDate, selected)

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
                
            tables = GS_history(company, product, startDate, endDate)
            if isinstance(tables, dict):
                tables = [tables]

            tables = list(tables)[::-1]
            context['response_tables'] = tables
            return render(request, 'search.html', context)

        elif selected == 'similar':
            try:
                result = run_openai_GPT(comment, startDate, endDate)  # ← 인사 프롬프트 호출
                if isinstance(result, dict):
                    result = [result]
                context['response_tables'] = result[::-1]
                print(result)
            except Exception as e:
                print("[ERROR] GPT 처리 중 오류:", e)
                context['response'] = "GPT 응답 중 오류가 발생했습니다."
                
            return render(request, 'search.html', context)
                
    # GET 요청 또는 POST 실패 시
    return render(request, 'search.html')
