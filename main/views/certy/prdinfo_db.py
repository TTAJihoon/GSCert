from django.http import JsonResponse

from main.models import SwData


def lookup_cert_info(request):
    cert_no = request.GET.get('cert_no')

    if not cert_no:
        return JsonResponse({'success': False, 'message': '제품 번호가 필요합니다.'}, status=400)

    try:
        obj = (
            SwData.objects.using('reference')
            .filter(test_number=cert_no)
            .values('cert_number', 'product', 'total_wd')
            .first()
        )

        if obj:
            data = {
                'cert_id': obj['cert_number'],
                'product_name': obj['product'],
                'total_wd': obj['total_wd'],
            }
            return JsonResponse({'success': True, 'data': data})
        else:
            return JsonResponse({'success': False, 'message': '해당 번호의 제품을 찾을 수 없습니다.'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'데이터베이스 조회 중 오류 발생: {e}'}, status=500)
