import sqlite3
from django.http import JsonResponse
from pathlib import Path
import os

def lookup_cert_info(request):
    cert_no = request.GET.get('cert_no')

    if not cert_no:
        return JsonResponse({'success': False, 'message': '제품 번호가 필요합니다.'}, status=400)

    try:
        db_path = 'main/data/reference.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        query = "SELECT 인증번호, 제품, 총WD FROM sw_data WHERE 시험번호 = ?"
        cursor.execute(query, (cert_no,))
        
        result = cursor.fetchone()
        conn.close()

        if result:
            data = {
                'cert_id': result[0],
                'product_name': result[1],
                'total_wd': result[2]
            }
            return JsonResponse({'success': True, 'data': data})
        else:
            return JsonResponse({'success': False, 'message': '해당 번호의 제품을 찾을 수 없습니다.'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'데이터베이스 조회 중 오류 발생: {e}'}, status=500)
