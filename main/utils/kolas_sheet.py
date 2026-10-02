"""KOLAS 점검 페이지(/kolas/)용 구글시트 파서.

기존 ecm_reference_sheet.parse_sheet_projects 는 2026년 시트의 최신 서식(TTA-YY-NNNNN,
"가. 일시" 바로 3행 아래가 데이터)만 읽는다. 2025년 시트(그리고 2026년 1~2월 회차)는
GS-A-25-0077 형식 번호 + 헤더 위치가 달라 기존 파서로는 통째로 버려진다. 기존 ECM 점검
페이지의 동작을 건드리지 않도록, KOLAS 전용으로 두 서식을 모두 읽는 파서를 따로 둔다.

- 번호 형식: TTA-26-01716 / GS-A-25-0077 (둘 다)
- 한 셀에 번호가 여러 줄이면(원시험 + 추가시험) 마지막 줄의 번호가 프로젝트다. 다른 칸도 마지막 줄 값을 쓴다.
- 헤더 위치: "순번" 헤더 행을 찾아 그 다음 행부터 데이터로 읽는다(빈 줄 개수와 무관).
- 대상 기간: '종료예정일'(G열) 기준.
- 중복 번호: 가장 최근 것 = 최신 시트 우선, 같은 시트 안에서는 행 번호가 작은 것
  (시트가 최신 회차부터 위에서 아래로 쌓이는 구조라서).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from main.utils.ecm_reference_sheet import (
    DEFAULT_SPREADSHEET_ID,
    build_pl_center_map,
    normalize_person_name,
    split_company_product,
)

logger = logging.getLogger(__name__)

SPREADSHEET_ID = DEFAULT_SPREADSHEET_ID
# 우선순위 순서(최신 시트 먼저). 같은 프로젝트번호가 둘 다에 있으면 앞쪽이 이긴다.
KOLAS_SHEETS = (
    ("2026", "740274777"),
    ("2025", "1283834444"),
)
RANGE_START = date(2025, 5, 14)
RANGE_END = date(2026, 9, 23)

# TTA-26-01716 / GS-A-25-0077 / GS-C-25-0077
PROJECT_NUMBER_RE = re.compile(r"[A-Z]{2,5}(?:-[A-Z])?-\d{2}-\d{4,5}")
# 시트 날짜 셀: "25/12/17,수" (yy/mm/dd,요일)
SHEET_DATE_RE = re.compile(r"^\s*(\d{2})/(\d{1,2})/(\d{1,2})")
SHEET_DATE_TOKEN_RE = re.compile(r"\d{2}/\d{1,2}/\d{1,2}(?:\s*,\s*[가-힣])?")
# 위원회 일시 셀 서식: "2025년 12월 29일(월)" / "2026. 9. 28" (점 구분은 2026-09부터 사용).
# 기존 ECM 점검 페이지 파서와 독립적으로 동작하도록 이 모듈 안에서 따로 해석한다.
COMMITTEE_DATE_RE = re.compile(r"^\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\([^)]*\))?.*$")
COMMITTEE_DATE_DOT_RE = re.compile(r"^\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*$")
# 시험원 셀 구분자: "황현후,조원진" / "우수진.박형준" / "A B". 이름 뒤 "(공공)", "(의료)" 같은 부서 표기는 제거.
TESTER_SPLIT_RE = re.compile(r"[,，、/·.\s]+")
TESTER_PAREN_RE = re.compile(r"\([^)]*\)")
HEADER_LABEL = "순번"
HEADER_SEARCH_LIMIT = 12


@dataclass
class KolasSheetRow:
    project_number: str
    cert_date: str
    cert_committee_date: date
    company: str
    product: str
    wd: str
    request_date: str
    contract_date: str
    start_date: str
    expected_end_date: str
    expected_end_on: date | None
    pl: str
    primary_tester: str
    center_code: str
    center_label: str
    raw_company_product: str
    source_gid: str
    source_row_number: int
    source_payload: dict = field(default_factory=dict)


def parse_cert_committee_date(value):
    text = str(value or "")
    match = COMMITTEE_DATE_RE.match(text) or COMMITTEE_DATE_DOT_RE.match(text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_sheet_date(value):
    """'25/12/17,수' → date(2025,12,17). 점 구분('2026. 9. 7') 등 위원회 서식도 허용."""
    text = str(value or "")
    match = SHEET_DATE_RE.match(text)
    if match:
        yy, month, day = (int(part) for part in match.groups())
        try:
            return date(2000 + yy, month, day)
        except ValueError:
            return None
    return parse_cert_committee_date(text)


def parse_kolas_sheet(csv_rows, *, gid="", center_map=None):
    """시트 한 장을 읽어 (KolasSheetRow 목록, 경고 목록)을 반환한다. 행 순서는 시트 순서."""
    center_map = center_map or build_pl_center_map()
    rows = []
    warnings = []

    row_index = 0
    while row_index < len(csv_rows):
        row = csv_rows[row_index]
        committee_date = parse_cert_committee_date(_cell(row, 1))
        if not committee_date:
            row_index += 1
            continue

        header_index = _find_header_row(csv_rows, row_index)
        if header_index is None:
            warnings.append(
                f"{gid} row={row_index + 1}: '{HEADER_LABEL}' 헤더 행을 찾지 못해 이 회차를 건너뜁니다 "
                f"({_cell(row, 1)!r})"
            )
            row_index += 1
            continue

        data_index = header_index + 1
        while data_index < len(csv_rows):
            data_row = csv_rows[data_index]
            b_value = _cell(data_row, 1)
            if not b_value or parse_cert_committee_date(b_value):
                break
            rows.extend(
                _parse_data_row(
                    data_row,
                    committee_date=committee_date,
                    gid=gid,
                    source_row_number=data_index + 1,
                    center_map=center_map,
                )
            )
            data_index += 1
        row_index = max(data_index, row_index + 1)

    return rows, warnings


def merge_sheets(parsed_by_sheet):
    """시트별 파싱 결과를 합치며 중복 프로젝트번호를 '가장 최근 것'으로 정리한다.

    parsed_by_sheet: KOLAS_SHEETS 우선순위 순서의 [KolasSheetRow 목록, ...].
    반환: (중복 제거된 목록, 버려진 중복 [(번호, 채택 gid/row, 제외 gid/row)]).
    """
    chosen = {}
    dropped = []
    for sheet_rows in parsed_by_sheet:
        for row in sorted(sheet_rows, key=lambda item: item.source_row_number):
            kept = chosen.get(row.project_number)
            if kept is None:
                chosen[row.project_number] = row
            else:
                dropped.append((
                    row.project_number,
                    f"{kept.source_gid}:{kept.source_row_number}",
                    f"{row.source_gid}:{row.source_row_number}",
                ))
    return list(chosen.values()), dropped


def filter_by_expected_end(rows, start=RANGE_START, end=RANGE_END):
    """종료예정일이 [start, end] 인 행만. 날짜를 못 읽은 행은 별도 반환."""
    selected = []
    undated = []
    for row in rows:
        if row.expected_end_on is None:
            undated.append(row)
        elif start <= row.expected_end_on <= end:
            selected.append(row)
    return selected, undated


def _find_header_row(csv_rows, date_row_index):
    for index in range(date_row_index + 1, min(date_row_index + 1 + HEADER_SEARCH_LIMIT, len(csv_rows))):
        if _cell(csv_rows[index], 0) == HEADER_LABEL:
            return index
        # 다음 회차가 먼저 나오면 헤더 없는 회차다.
        if parse_cert_committee_date(_cell(csv_rows[index], 1)):
            return None
    return None


def resolve_primary_tester(tester, center_map):
    """시험원 셀에서 대표 PL 이름을 정한다. 센터가 배정된 첫 이름을 우선하고, 없으면 첫 이름."""
    names = [
        normalize_person_name(TESTER_PAREN_RE.sub("", token))
        for token in TESTER_SPLIT_RE.split(str(tester or ""))
    ]
    names = [name for name in names if name]
    for name in names:
        if name in center_map:
            return name
    return names[0] if names else ""


def _parse_data_row(row, *, committee_date, gid, source_row_number, center_map):
    """데이터 행 1개를 프로젝트 1건으로 읽는다.

    프로젝트 번호 셀에 번호가 여러 줄(원시험 + 추가시험 등)로 들어 있으면 **마지막 줄의 번호**가 이 행의 프로젝트다.
    앞쪽 번호는 이전 시험의 번호라 ECM 에서 같은 폴더로 찾을 수 없다. 그 경우 WD·시작일·종료예정일 등 다른 칸도
    번호와 같은 순서로 줄이 나뉘어 있으므로 마지막 프로젝트에 해당하는 마지막 줄 값을 쓴다.
    """
    raw_company_product = _cell(row, 1)
    project_number_cell = _cell(row, 8)
    if not raw_company_product:
        return []
    numbers = list(dict.fromkeys(PROJECT_NUMBER_RE.findall(project_number_cell)))
    if not numbers:
        return []
    project_number = numbers[-1]
    count = len(numbers)

    if count > 1:
        company_product = _aligned_or_whole(raw_company_product, count)
        tester = _aligned_or_whole(_cell(row, 7), count)
        wd = _last_line(_cell(row, 2))
        request_date = _last_date(_cell(row, 3))
        contract_date = _last_date(_cell(row, 4))
        start_date = _last_date(_cell(row, 5))
        expected_end_date = _last_date(_cell(row, 6))
    else:
        company_product = raw_company_product
        tester = _cell(row, 7)
        wd = _first_line(_cell(row, 2))
        request_date = _first_line(_cell(row, 3))
        contract_date = _first_line(_cell(row, 4))
        start_date = _first_line(_cell(row, 5))
        expected_end_date = _first_line(_cell(row, 6))

    company, product = split_company_product(company_product)
    primary_tester = resolve_primary_tester(tester, center_map)
    center_code, center_label = center_map.get(primary_tester, ("unknown", "미분류"))

    return [
        KolasSheetRow(
            project_number=project_number,
            cert_date=f"{committee_date.month}/{committee_date.day}",
            cert_committee_date=committee_date,
            company=company,
            product=product,
            wd=wd,
            request_date=request_date,
            contract_date=contract_date,
            start_date=start_date,
            expected_end_date=expected_end_date,
            expected_end_on=parse_sheet_date(expected_end_date),
            pl=tester,
            primary_tester=primary_tester,
            center_code=center_code,
            center_label=center_label,
            raw_company_product=company_product,
            source_gid=str(gid),
            source_row_number=source_row_number,
            source_payload={
                "B": raw_company_product,
                "C": _cell(row, 2),
                "D": _cell(row, 3),
                "E": _cell(row, 4),
                "F": _cell(row, 5),
                "G": _cell(row, 6),
                "H": _cell(row, 7),
                "I": project_number_cell,
            },
        )
    ]


def _lines(value):
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _first_line(value):
    return value.splitlines()[0].strip() if value else value


def _last_line(value):
    lines = _lines(value)
    return lines[-1] if lines else str(value or "").strip()


def _last_date(value):
    """셀 안의 마지막 날짜 토큰. 줄바꿈 대신 공백으로 이어 붙인 경우("25/10/10,금 25/11/06,목")도 읽는다."""
    tokens = SHEET_DATE_TOKEN_RE.findall(str(value or ""))
    return tokens[-1].strip() if tokens else _last_line(value)


def _aligned_or_whole(value, count):
    """줄 수가 프로젝트 번호 수와 같으면(프로젝트마다 한 줄씩) 마지막 줄, 아니면 셀 전체.

    회사(제품) 칸처럼 번호와 무관하게 줄바꿈이 들어가는 칸을 잘못 자르지 않기 위한 보수적인 규칙이다.
    """
    lines = _lines(value)
    if count > 1 and len(lines) == count:
        return lines[-1]
    return str(value or "").strip()


def _cell(row, index):
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()
