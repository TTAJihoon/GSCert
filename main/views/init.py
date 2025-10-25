from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def welcome(request):
    return render(request, 'welcome.html')

def login_test_view(request):
    return render(request, 'registration/login.html')

def index(request):
    return render(request, 'index.html')


def history(request):
    return render(request, 'testing/history.html')

def similar(request):
    return render(request, 'testing/similar.html')
    
def security(request):
    return render(request, 'testing/security.html')


def prdinfo(request):
    return render(request, 'certy/prdinfo.html')


def checkreport(request):
    return render(request, 'checkreport.html')
    
def test(request):
    return render(request, 'test.html')
