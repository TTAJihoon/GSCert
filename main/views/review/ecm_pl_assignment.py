"""'PL 배정 목록' 기능의 비즈니스 로직.

launcher.ps1의 'G' 메뉴(sync_reference_projects_from_sheet --assign-unknown-pl)가
서버 터미널에서 input()으로 하던 PL-센터 재배정을, 산출물 점검 프로젝트 목록
페이지의 'PL 배정 목록' 모달에서 하게 한다.
"""

from django.conf import settings
from django.db import transaction
from django.db.models import Count

from main.models import ReferenceCenterPl, ReferenceProject
from main.utils.ecm_reference_sheet import normalize_person_name
from main.views.review.ecm_download_review_centers import center_choices

UNASSIGNED_CENTER_CODE = "unknown"
UNASSIGNED_CENTER_LABEL = "미배정"


class PlAssignmentError(ValueError):
    error_code = "invalid_pl_assignment"
    status_code = 400

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details or {}


def _reference_db_alias():
    return getattr(settings, "REFERENCE_DATABASE_ALIAS", "reference")


def _center_label_map():
    labels = {choice["code"]: choice["label"] for choice in center_choices()}
    labels[UNASSIGNED_CENTER_CODE] = UNASSIGNED_CENTER_LABEL
    return labels


def get_pl_assignment_payload():
    """센터(+미배정)별 PL 목록과 각 PL이 담당 중인 프로젝트 개수를 반환한다."""
    alias = _reference_db_alias()
    label_map = _center_label_map()
    centers = [{"code": code, "label": label} for code, label in label_map.items()]
    assignments = {code: [] for code in label_map}

    project_counts = {
        (normalize_person_name(row["primary_tester"]), row["center_code"]): row["project_count"]
        for row in (
            ReferenceProject.objects.using(alias)
            .exclude(primary_tester="")
            .values("primary_tester", "center_code")
            .annotate(project_count=Count("id"))
        )
    }

    # 센터에 이미 배정된 PL(ReferenceCenterPl에 등록된 이름).
    for pl_row in ReferenceCenterPl.objects.using(alias).all():
        if pl_row.center_code not in assignments:
            continue
        key = (normalize_person_name(pl_row.name), pl_row.center_code)
        assignments[pl_row.center_code].append({
            "name": pl_row.name,
            "project_count": project_counts.get(key, 0),
        })

    # 미배정: ReferenceCenterPl에 없어 center_code='unknown'으로 적재된 담당자.
    # review_result가 비어있지 않은(이미 점검된) 프로젝트는 세지 않는다 - PL을
    # 센터에 배정할 때 함께 따라가지 않고 그대로 남기 때문(아래 apply 쪽 주석 참고).
    unassigned_rows = (
        ReferenceProject.objects.using(alias)
        .filter(center_code=UNASSIGNED_CENTER_CODE, review_result="")
        .exclude(primary_tester="")
        .values("primary_tester")
        .annotate(project_count=Count("id"))
    )
    for row in unassigned_rows:
        assignments[UNASSIGNED_CENTER_CODE].append({
            "name": row["primary_tester"],
            "project_count": row["project_count"],
        })

    for code in assignments:
        assignments[code].sort(key=lambda item: (-item["project_count"], item["name"]))

    return {"success": True, "centers": centers, "assignments": assignments}


def apply_pl_assignment_changes(changes):
    """PL 배정 변경 목록을 적용한다.

    changes: [{"name": str, "from_center": str, "to_center": str}, ...]

    규칙(사용자 확정):
    - 미배정 -> 센터: 매핑을 새로 만들고, 이미 등록된 미배정(unknown) 프로젝트 중
      아직 점검하지 않은(review_result가 비어있는) 것만 즉시 새 센터로 옮긴다.
      이미 점검된 프로젝트는 미배정 상태 그대로 둔다 - A센터에서 점검까지 마친
      프로젝트인데 그 PL이 이후 미배정으로 옮겨지면(그리고 다음 시트 동기화가
      center_code를 'unknown'으로 덮어쓰면) review_result는 그대로 남아있으므로,
      이걸로 "이미 점검됨"을 구분해 자동으로 새 센터에 휩쓸려 들어가지 않게 한다.
    - 센터 -> 다른 센터: 매핑만 갱신한다. 기존 프로젝트는 그대로 두고 다음 시트
      동기화부터 새 센터로 적재된다.
    - 센터 -> 미배정: 매핑을 삭제한다(기존 프로젝트는 그대로 둠).
    """
    if not isinstance(changes, list) or not changes:
        raise PlAssignmentError("적용할 변경 사항이 없습니다.")

    alias = _reference_db_alias()
    label_map = _center_label_map()
    valid_codes = set(label_map)

    normalized_changes = []
    for raw in changes:
        if not isinstance(raw, dict):
            raise PlAssignmentError("변경 항목 형식이 올바르지 않습니다.")
        name = str(raw.get("name") or "").strip()
        to_center = str(raw.get("to_center") or "").strip()
        from_center = str(raw.get("from_center") or "").strip()
        if not name:
            raise PlAssignmentError("PL 이름이 비어 있는 변경 항목이 있습니다.")
        if to_center not in valid_codes:
            raise PlAssignmentError(f"지원하지 않는 센터입니다: {to_center}")
        if from_center and from_center not in valid_codes:
            raise PlAssignmentError(f"지원하지 않는 센터입니다: {from_center}")
        if to_center == from_center:
            continue
        normalized_changes.append({"name": name, "from_center": from_center, "to_center": to_center})

    moved_project_count = 0
    updated_pl_count = 0

    with transaction.atomic(using=alias):
        for change in normalized_changes:
            name = change["name"]
            from_center = change["from_center"]
            to_center = change["to_center"]

            if to_center == UNASSIGNED_CENTER_CODE:
                deleted, _detail = ReferenceCenterPl.objects.using(alias).filter(name=name).delete()
                if deleted:
                    updated_pl_count += 1
                continue

            to_label = label_map[to_center]
            existing = ReferenceCenterPl.objects.using(alias).filter(name=name).first()
            if existing:
                if existing.center_code != to_center:
                    existing.center_code = to_center
                    existing.center_label = to_label
                    existing.save(using=alias, update_fields=["center_code", "center_label", "updated_at"])
                    updated_pl_count += 1
            else:
                next_order = (
                    ReferenceCenterPl.objects.using(alias).filter(center_code=to_center).count() + 1
                )
                ReferenceCenterPl.objects.using(alias).create(
                    center_code=to_center,
                    center_label=to_label,
                    name=name,
                    display_order=next_order,
                )
                updated_pl_count += 1

            if from_center == UNASSIGNED_CENTER_CODE:
                moved_project_count += (
                    ReferenceProject.objects.using(alias)
                    .filter(center_code=UNASSIGNED_CENTER_CODE, primary_tester=name, review_result="")
                    .update(center_code=to_center, center_label=to_label)
                )

    payload = get_pl_assignment_payload()
    payload.update({
        "updated_pl_count": updated_pl_count,
        "moved_project_count": moved_project_count,
    })
    return payload
