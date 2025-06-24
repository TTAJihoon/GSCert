def reload_reference_view(request):
    reload_reference_context()
    reload_reference_dataframe()
    return render(request, 'index.html', {
        'response': 'reference.csv 파일이 다시 로드되었습니다.'
    })
