from django.shortcuts import render
from .chatbot  import run_ollama_model  # 내부 모듈에서 함수 가져오기

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
