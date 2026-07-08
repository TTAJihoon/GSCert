import re

from django.shortcuts import render

from main.models import SwData
from main.request_logging import set_request_log_context


def _cert_date_sort_key(row):
    """인증일자를 실제 날짜 순으로 정렬하기 위한 키.

    sw_data.cert_date 는 '2026.6.8' 처럼 0-패딩 없는 텍스트라, 문자열 정렬 시
    '2026.6.8' 이 '2026.6.29' 보다 크게(최신으로) 잡힌다. 숫자(연,월,일)를 뽑아
    튜플로 비교해 올바른 날짜 순서를 만든다. (파싱 불가 시 맨 뒤로)
    """
    nums = re.findall(r"\d+", str(row.get("인증일자") or ""))
    if len(nums) >= 3:
        return (int(nums[0]), int(nums[1]), int(nums[2]))
    return (0, 0, 0)

_FIELD_TO_KR = {
    'serial_number': '일련번호',
    'cert_number': '인증번호',
    'cert_date': '인증일자',
    'company': '회사명',
    'product': '제품',
    'grade': '등급',
    'test_number': '시험번호',
    'sw_category': 'SW분류',
    'product_desc': '제품설명',
    'total_wd': '총WD',
    'renewal': '재계약',
    'notes': '특이사항',
    'date_range': '시작날짜종료날짜',
    'test_lab': '시험원',
    'start_date': '시작일자',
    'end_date': '종료일자',
    'recert_type': '재인증구분',
    'prev_cert_info': '기인증번호제품정보버전',
}


def history(request):
    if request.method == 'POST':
        gsnum = request.POST.get('gsnum', '')
        project = request.POST.get('project', '')
        company = request.POST.get('company', '')
        product = request.POST.get('product', '')
        sw_type = request.POST.get('sw_type', '')
        tester = request.POST.get('tester', '')
        startDate = request.POST.get('start_date', '')
        endDate = request.POST.get('end_date', '')
        comment = request.POST.get('comment', '')
        search_terms = _search_terms(
            comment=comment,
            company=company,
            product=product,
            sw_type=sw_type,
            tester=tester,
            start_date=startDate,
            end_date=endDate,
            gsnum=gsnum,
            project=project,
        )
        set_request_log_context(
            request,
            feature="history",
            search=search_terms,
        )

        context = {
            'gsnum': gsnum,
            'project': project,
            'company': company,
            'product': product,
            'sw_type': sw_type,
            'tester': tester,
            'start_date': startDate,
            'end_date': endDate,
            'comment': comment,
        }

        tables = GS_history(gsnum, project, company, product, sw_type, tester, comment, startDate, endDate)
        set_request_log_context(request, result_count=len(tables))

        clean_tables = []
        for table in tables:
            clean_table = {
                key.strip().replace(" ", "_").replace("/", "_").replace("\n", "_"): str(value).strip().replace("None", "-")
                for key, value in table.items()
                if not key.startswith('Unnamed')
            }
            clean_tables.append(clean_table)

        # 인증일자 내림차순(최신순) 정렬 — 예전의 단순 역순([::-1])은 DB 기본 순서에
        # 의존해 최신(예: 6.29)이 목록 맨 아래로 밀리는 문제가 있었다.
        clean_tables.sort(key=_cert_date_sort_key, reverse=True)
        context['response_tables'] = clean_tables

        return render(request, 'testing/history.html', context)

    return render(request, 'testing/history.html')


def _search_terms(**terms):
    return {
        key: value.strip()
        for key, value in terms.items()
        if isinstance(value, str) and value.strip()
    }


def GS_history(gsnum='', project='', company='', product='', sw_type='', tester='', comment='', startDate='', endDate=''):
    qs = SwData.objects.using('reference')

    if gsnum.strip():
        qs = qs.filter(cert_number__icontains=gsnum)
    if project.strip():
        qs = qs.filter(test_number__icontains=project)
    if company.strip():
        qs = qs.filter(company__icontains=company)
    if product.strip():
        qs = qs.filter(product__icontains=product)
    if sw_type.strip():
        qs = qs.filter(sw_category__icontains=sw_type)
    if tester.strip():
        qs = qs.filter(test_lab__icontains=tester)
    if comment.strip():
        qs = qs.filter(product_desc__icontains=comment)
    if startDate.strip():
        qs = qs.filter(start_date__gte=startDate)
    if endDate.strip():
        qs = qs.filter(end_date__lte=endDate)

    return [
        {_FIELD_TO_KR[k]: v for k, v in obj.items() if k in _FIELD_TO_KR}
        for obj in qs.values()
    ]
