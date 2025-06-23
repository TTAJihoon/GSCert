from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def welcome(request):
    return render(request, 'welcome.html')

def login_test_view(request):
    return render(request, 'registration/login.html')

def index(request):
    return render(request, 'index.html')

def security(request):
    return render(request, 'security.html')

def genspark(request):
    return render(request, 'genspark.html')
