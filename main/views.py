from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def welcome(request):
    return render(request, 'main/welcome.html')

def login_test_view(request):
    return render(request, 'main/registration/login.html')
