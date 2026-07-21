import re

from django.db.models import Q
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
    'kolas': 'KOLAS',
}

# '특이사항' 열의 버튼 판정 규칙
_RENEWAL_PLACEHOLDER = '재계약된 경우 기재\n(메모 참조)'
_NOTES_PLACEHOLDER = 'WD 이슈사항 기재\n(메모 참조)'
_EXCLUDE_SUBSTRINGS = ('없음', 'N', 'X')
_EXCLUDE_EXACT = ('-',)


def _has_meaningful_value(value: str, placeholder: str) -> bool:
    """안내 문구(placeholder)/'-'/'없음'·'N'·'X' 포함값을 제외하고 실제 값인지 판정한다."""
    return (
        bool(value)
        and value != placeholder
        and value not in _EXCLUDE_EXACT
        and not any(marker in value for marker in _EXCLUDE_SUBSTRINGS)
    )


def _build_notes_buttons(row: dict) -> list[dict]:
    """'특이사항' 열에 표시할 버튼 목록을 구성한다.

    1. 재인증: 재인증구분(O)에 '재인증'이 포함되면 표시. 툴팁 = '재인증구분값\n기인증번호제품정보버전값'
    2. 재계약: 재계약(K)이 안내 문구(placeholder)/'-'가 아니고, 공백도 아니고,
       '없음'/'N'/'X'를 포함하지 않으면 표시. 툴팁 = 재계약값
    3. KOLAS: KOLAS(Q)에 'KOLAS'가 포함되면 표시. 툴팁 없음.
    4. 특이사항: 특이사항(L)이 재계약과 같은 기준(안내 문구/'-'/'없음'·'N'·'X' 제외)으로
       실제 값이면 표시. 툴팁 = 특이사항값
    """
    buttons = []

    recert_type = (row.get('재인증구분') or '').strip()
    if '재인증' in recert_type:
        prev_cert_info = (row.get('기인증번호제품정보버전') or '').strip()
        buttons.append({
            'type': 'recert',
            'label': '재인증',
            'tooltip': f"{recert_type}\n{prev_cert_info}",
        })

    renewal = (row.get('재계약') or '').strip()
    if _has_meaningful_value(renewal, _RENEWAL_PLACEHOLDER):
        buttons.append({'type': 'renewal', 'label': '재계약', 'tooltip': renewal})

    kolas = (row.get('KOLAS') or '').strip()
    if 'KOLAS' in kolas:
        buttons.append({'type': 'kolas', 'label': 'KOLAS', 'tooltip': None})

    notes = (row.get('특이사항') or '').strip()
    if _has_meaningful_value(notes, _NOTES_PLACEHOLDER):
        buttons.append({'type': 'notes', 'label': '특이사항', 'tooltip': notes})

    return buttons


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
            clean_table['특이사항_버튼'] = _build_notes_buttons(table)
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
    # 날짜 범위 필터는 값이 있는 행에만 적용한다. sw_data 의 start_date/end_date 는
    # 비어 있는 행이 많은데(예: 최근 등록분), 폼이 기본 날짜를 항상 채워 제출하므로
    # 단순 __gte/__lte 로 걸면 '날짜가 빈 행'이 전부 제외돼 검색 결과가 사라진다.
    # → 빈 날짜(미기재) 행은 날짜 조건으로 배제하지 않는다.
    if startDate.strip():
        qs = qs.filter(Q(start_date__gte=startDate) | Q(start_date=""))
    if endDate.strip():
        qs = qs.filter(Q(end_date__lte=endDate) | Q(end_date=""))

    return [
        {_FIELD_TO_KR[k]: v for k, v in obj.items() if k in _FIELD_TO_KR}
        for obj in qs.values()
    ]
