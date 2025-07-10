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
            try:
                print(comment, startDate, endDate)
                # response_text = run_openai_GPT(comment, startDate, endDate)  # ← 인사 프롬프트 호출
                # context['response'] = response_text       # 문자열 응답은 'response'에 담아 렌더링
                context['response'] = "";
            except Exception as e:
                print("[ERROR] GPT 처리 중 오류:", e)
                context['response'] = "GPT 응답 중 오류가 발생했습니다."
                
            return render(request, 'index.html', context)
                
    # GET 요청 또는 POST 실패 시
    return render(request, 'index.html')
