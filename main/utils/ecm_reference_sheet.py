import csv
import re
from dataclasses import dataclass
from datetime import date
from io import StringIO
from urllib.request import urlopen


DEFAULT_SPREADSHEET_ID = "1KvzcX3zVJmUx02iIogRj0sRjGD1o7ae4xuX2DFGn_T8"
DEFAULT_GID = "740274777"

CENTER_PL_NAMES = {
    "bundang": {
        "label": "분당",
        "names": [
            "임우섭", "구자경", "박현권", "박상욱", "강지성", "임성은", "노남규", "김수경",
            "최재은", "이은지", "강준혁", "임현지", "장현영", "이예정", "이상현", "권용진",
            "윤나연", "남승윤",
        ],
    },
    "sangam": {
        "label": "상암",
        "names": [
            "김진영", "곽행신", "엄태호", "정광락", "최민경", "엄경숙", "유지영", "최유정",
            "박지훈", "우수진", "윤성복", "정승용", "김도균", "박형준", "이수민", "박지인",
            "윤희정", "석민경", "윤소민", "장진아", "김윤아", "한수민", "이준구", "조혜령",
            "윤상일",
        ],
    },
    "yeongnam": {
        "label": "영남",
        "names": [
            "이재훈", "전지은", "김민우", "이진협", "김태호", "황현후", "강미진", "이진호",
            "김현규", "조원진", "조은하",
        ],
    },
}

DATE_RE = re.compile(r"^\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\([^)]*\))?.*$")
PAREN_RE = re.compile(r"\([^)]*\)")
# 회사명 맨 앞의 "(주)/(유)/(재)/(사)"는 영문명 등 부가 표기가 아니라 법인 표시 자체라
# PAREN_RE로 지우면 안 된다(예: "(주)헬스맥스" → "헬스맥스"로 잘못 잘리는 문제).
LEADING_ENTITY_PAREN_RE = re.compile(r"^\((주|유|재|사|합자|합명)\)")
PROJECT_NUMBER_RE = re.compile(r"^[A-Z]{2,5}-\d{2}-\d{4,5}$")


@dataclass(frozen=True)
class SheetProjectRow:
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
    pl: str
    primary_tester: str
    center_code: str
    center_label: str
    raw_company_product: str
    source_row_number: int
    source_payload: dict


def download_sheet_csv(spreadsheet_id=DEFAULT_SPREADSHEET_ID, gid=DEFAULT_GID, timeout=30):
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def read_csv_rows(csv_text):
    return [row for row in csv.reader(StringIO(csv_text))]


def build_pl_center_map(center_pl_names=None):
    mapping = {}
    source = center_pl_names or CENTER_PL_NAMES
    for center_code, definition in source.items():
        for name in definition["names"]:
            mapping[normalize_person_name(name)] = (center_code, definition["label"])
    return mapping


def parse_sheet_projects(csv_rows, center_map=None):
    center_map = center_map or build_pl_center_map()
    projects = []

    for row_index, row in enumerate(csv_rows):
        cert_committee_date = parse_cert_committee_date(_cell(row, 1))
        if not cert_committee_date:
            continue

        data_index = row_index + 3
        while data_index < len(csv_rows):
            data_row = csv_rows[data_index]
            b_value = _cell(data_row, 1)
            if not b_value or parse_cert_committee_date(b_value):
                break

            parsed = parse_project_row(
                data_row,
                cert_committee_date=cert_committee_date,
                source_row_number=data_index + 1,
                center_map=center_map,
            )
            if parsed:
                projects.append(parsed)
            data_index += 1

    return projects


def parse_project_row(row, *, cert_committee_date, source_row_number, center_map):
    raw_company_product = _cell(row, 1)
    project_number = _cell(row, 8)
    if not raw_company_product or not PROJECT_NUMBER_RE.match(project_number):
        return None

    company, product = split_company_product(raw_company_product)
    tester = _cell(row, 7)
    primary_tester = first_tester_name(tester)
    center_code, center_label = center_map.get(primary_tester, ("unknown", "미분류"))

    return SheetProjectRow(
        project_number=project_number,
        cert_date=f"{cert_committee_date.month}/{cert_committee_date.day}",
        cert_committee_date=cert_committee_date,
        company=company,
        product=product,
        wd=_cell(row, 2),
        request_date=_cell(row, 3),
        contract_date=_cell(row, 4),
        start_date=_cell(row, 5),
        expected_end_date=_cell(row, 6),
        pl=tester,
        primary_tester=primary_tester,
        center_code=center_code,
        center_label=center_label,
        raw_company_product=raw_company_product,
        source_row_number=source_row_number,
        source_payload={
            "B": raw_company_product,
            "C": _cell(row, 2),
            "D": _cell(row, 3),
            "E": _cell(row, 4),
            "F": _cell(row, 5),
            "G": _cell(row, 6),
            "H": tester,
            "I": project_number,
        },
    )


def parse_cert_committee_date(value):
    match = DATE_RE.match(str(value or ""))
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    return date(year, month, day)


def split_company_product(value):
    text = str(value or "")
    leading_entity = LEADING_ENTITY_PAREN_RE.match(text)
    prefix = ""
    if leading_entity:
        prefix = leading_entity.group(0)
        text = text[leading_entity.end():]
    cleaned = PAREN_RE.sub("", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if "-" not in cleaned:
        return (prefix + cleaned).strip(), ""
    company, product = cleaned.split("-", 1)
    return (prefix + company.strip()).strip(), product.strip()


def first_tester_name(value):
    first = re.split(r"[,，、/]", str(value or ""), maxsplit=1)[0]
    return normalize_person_name(first)


def normalize_person_name(value):
    return re.sub(r"\s+", "", str(value or "").strip())


def _cell(row, index):
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()
