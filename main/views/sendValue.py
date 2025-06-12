from django.shortcuts import render
import subprocess
import os

def chat_gpt(request):
    if request.method == 'POST':
        q1 = request.POST.get('company', '')
        q2 = request.POST.get('product', '')
        q3 = request.POST.get('startDate', '')
        q4 = request.POST.get('endDate', '')
        q5 = request.POST.get('comment', '')

        # ollama 파이썬 파일 경로
        file_path = os.path.join('C:/GSCert/myproject/main/views/chatbot', 'chatbot.py')
        try:
            result = subprocess.run(
                ['python', file_path, q1, q2, q3, q4, q5],
                capture_output=True,
                text=True,
                check=True
            )
            return render(request, 'index.html', {'response': result.stdout})
        except subprocess.CalledProcessError as e:
            return render(request, 'index.html', {'response': f"에러 발생: {e.stderr}"})
    return render(request, 'index.html')
