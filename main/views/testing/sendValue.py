import json
import pandas as pd
from django.shortcuts import render
from .history import GS_history
from .similar_GPT import run_openai_GPT

def search_history(request):
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
            return render(request, 'search.html', context)
                
        tables = GS_history(gsnum, project, company, product, startDate, endDate)
        if isinstance(tables, dict):
            tables = [tables]

        tables = list(tables)[::-1]
        context['response_tables'] = tables
        return render(request, 'search.html', context)
               
    # GET 요청 또는 POST 실패 시
    return render(request, 'search.html')
