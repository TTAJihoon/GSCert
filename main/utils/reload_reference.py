import pandas as pd
from django.shortcuts import render
from main.utils.constants import REFERENCE_PATH

# 전역 DataFrame
REFERENCE_DF = None

def reload_reference_dataframe():
    global REFERENCE_DF
    try:
        REFERENCE_DF = pd.read_csv(REFERENCE_PATH, skiprows=3)
        print("[INFO] REFERENCE_DF reloaded.")
    except Exception as e:
        print("[ERROR] DataFrame reload 실패:", e)

# 초기 1회 로딩
#reload_reference_dataframe()

def get_REF():
    return REFERENCE_DF

def reload_reference_view(request):
    reload_reference_dataframe()
    return render(request, 'index.html', {
        'response': 'reference.csv 파일이 다시 로드되었습니다.'
    })
