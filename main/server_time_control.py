import ctypes
import json
import re
import time
from datetime import datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from main.models import ServerTimeAudit, ServerTimeControl, ServerTimeControlStatus


PIN_RE = re.compile(r"^\d{4}$")
KOREA_TZ = ZoneInfo("Asia/Seoul")
PIN_ATTEMPT_LIMIT = 5
PIN_ATTEMPT_WINDOW_MS = 60_000


class ServerTimeRequestError(ValueError):
    def __init__(self, message, *, code="invalid_request", status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def uptime_ms():
    if hasattr(ctypes, "windll"):
        return int(ctypes.windll.kernel32.GetTickCount64())
    return int(time.monotonic() * 1000)


def get_control():
    try:
        control, _ = ServerTimeControl.objects.get_or_create(id=1)
        return control
    except IntegrityError:
        return ServerTimeControl.objects.get(id=1)


def normal_time_estimate(control, *, current_uptime_ms=None):
    if control.normal_time_before_change is None or control.baseline_uptime_ms is None:
        return timezone.now()
    current_uptime_ms = current_uptime_ms if current_uptime_ms is not None else uptime_ms()
    if current_uptime_ms < control.baseline_uptime_ms:
        return None
    return control.normal_time_before_change + timedelta(
        milliseconds=current_uptime_ms - control.baseline_uptime_ms
    )


def public_payload(control=None):
    control = control or get_control()
    current_uptime = uptime_ms()
    normal_estimate = normal_time_estimate(control, current_uptime_ms=current_uptime)
    remaining = None
    if control.expires_uptime_ms is not None and control.status in {
        ServerTimeControlStatus.CHANGING,
        ServerTimeControlStatus.ACTIVE,
        ServerTimeControlStatus.RESTORING,
        ServerTimeControlStatus.RECOVERY_FAILED,
    }:
        remaining = max(0, (control.expires_uptime_ms - current_uptime + 999) // 1000)
    heartbeat_age = None
    if control.agent_heartbeat_uptime_ms is not None and current_uptime >= control.agent_heartbeat_uptime_ms:
        heartbeat_age = (current_uptime - control.agent_heartbeat_uptime_ms) // 1000
    return {
        "success": True,
        "status": control.status,
        "revision": control.revision,
        "server_time": timezone.now().isoformat(),
        "normal_time_estimate": normal_estimate.isoformat() if normal_estimate else None,
        "owner_name": control.owner_name,
        "target_time": control.target_time.isoformat() if control.target_time else None,
        "remaining_seconds": remaining,
        "agent_online": heartbeat_age is not None and heartbeat_age <= 5,
        "error_message": control.error_message if control.status == ServerTimeControlStatus.RECOVERY_FAILED else "",
        "can_set": control.status == ServerTimeControlStatus.IDLE,
        "can_owner_control": control.status in {
            ServerTimeControlStatus.ACTIVE,
            ServerTimeControlStatus.RECOVERY_FAILED,
        },
    }


def parse_request_body(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServerTimeRequestError("요청 형식이 올바르지 않습니다.") from exc
    if not isinstance(payload, dict):
        raise ServerTimeRequestError("요청 형식이 올바르지 않습니다.")
    return payload


def request_action(*, action, revision, owner_name, pin, target_value, requested_ip):
    owner_name = str(owner_name or "").strip()
    pin = str(pin or "")
    if not owner_name or len(owner_name) > 80:
        raise ServerTimeRequestError("이름을 입력해주세요.")
    if not PIN_RE.fullmatch(pin):
        raise ServerTimeRequestError("PIN은 숫자 4자리로 입력해주세요.")
    try:
        revision = int(revision)
    except (TypeError, ValueError) as exc:
        raise ServerTimeRequestError("화면을 새로 열어 다시 시도해주세요.", code="stale_revision", status_code=409) from exc

    control = get_control()
    if control.revision != revision:
        raise ServerTimeRequestError("다른 사용자가 먼저 상태를 변경했습니다.", code="stale_revision", status_code=409)

    if action == "change":
        if control.status != ServerTimeControlStatus.IDLE:
            raise ServerTimeRequestError("현재 다른 사용자가 서버 시간을 설정 중입니다.", code="lease_active", status_code=409)
        target = _parse_past_target(target_value, control)
        now = timezone.now()
        current_uptime = uptime_ms()
        updated = ServerTimeControl.objects.filter(
            id=1,
            status=ServerTimeControlStatus.IDLE,
            revision=revision,
        ).update(
            status=ServerTimeControlStatus.CHANGING,
            revision=F("revision") + 1,
            pending_action="change",
            owner_name=owner_name,
            pin_hash=make_password(pin),
            requested_ip=requested_ip or None,
            target_time=target,
            normal_time_before_change=now,
            baseline_uptime_ms=current_uptime,
            expires_uptime_ms=None,
            failed_pin_attempts=0,
            last_pin_failure_uptime_ms=None,
            error_message="",
        )
        if not updated:
            raise ServerTimeRequestError("다른 사용자가 먼저 상태를 변경했습니다.", code="stale_revision", status_code=409)
        control = get_control()
        record_audit(control, "change_requested", normal_estimate=now, detail={"target_time": target.isoformat()})
        return public_payload(control)

    if action not in {"reset", "restore"}:
        raise ServerTimeRequestError("지원하지 않는 작업입니다.")
    if control.status not in {ServerTimeControlStatus.ACTIVE, ServerTimeControlStatus.RECOVERY_FAILED}:
        raise ServerTimeRequestError("현재 변경 중인 서버 시간이 없습니다.", code="lease_not_active", status_code=409)
    _verify_owner(control, owner_name, pin)
    target = _parse_past_target(target_value, control) if action == "reset" else control.target_time
    next_status = ServerTimeControlStatus.CHANGING if action == "reset" else ServerTimeControlStatus.RESTORING
    updated = ServerTimeControl.objects.filter(id=1, status=control.status, revision=revision).update(
        status=next_status,
        revision=F("revision") + 1,
        pending_action=action,
        target_time=target,
        requested_ip=requested_ip or control.requested_ip,
        failed_pin_attempts=0,
        last_pin_failure_uptime_ms=None,
        error_message="",
    )
    if not updated:
        raise ServerTimeRequestError("다른 요청이 먼저 처리됐습니다.", code="stale_revision", status_code=409)
    control = get_control()
    record_audit(control, f"{action}_requested", detail={"target_time": target.isoformat() if target else None})
    return public_payload(control)


def _parse_past_target(value, control):
    try:
        target = datetime.strptime(str(value or ""), "%Y-%m-%dT%H:%M").replace(tzinfo=KOREA_TZ)
    except ValueError as exc:
        raise ServerTimeRequestError("날짜와 시간을 분 단위로 입력해주세요.") from exc
    if target.year < 1601:
        raise ServerTimeRequestError("Windows에서 지원하는 날짜를 입력해주세요.")
    normal_now = normal_time_estimate(control)
    if normal_now is None:
        raise ServerTimeRequestError("정상 기준 시각을 확인할 수 없어 변경할 수 없습니다.", code="normal_time_unavailable", status_code=503)
    if target.astimezone(datetime_timezone.utc) > normal_now.astimezone(datetime_timezone.utc):
        raise ServerTimeRequestError("미래 시간으로는 변경할 수 없습니다.")
    return target


def _verify_owner(control, owner_name, pin):
    current_uptime = uptime_ms()
    if (
        control.failed_pin_attempts >= PIN_ATTEMPT_LIMIT
        and control.last_pin_failure_uptime_ms is not None
        and current_uptime - control.last_pin_failure_uptime_ms < PIN_ATTEMPT_WINDOW_MS
    ):
        raise ServerTimeRequestError("PIN 입력을 잠시 후 다시 시도해주세요.", code="pin_rate_limited", status_code=429)
    if owner_name == control.owner_name and check_password(pin, control.pin_hash):
        return
    failures = control.failed_pin_attempts + 1
    if control.last_pin_failure_uptime_ms is None or current_uptime - control.last_pin_failure_uptime_ms >= PIN_ATTEMPT_WINDOW_MS:
        failures = 1
    ServerTimeControl.objects.filter(id=1, revision=control.revision).update(
        failed_pin_attempts=failures,
        last_pin_failure_uptime_ms=current_uptime,
    )
    record_audit(control, "pin_rejected", detail={"attempted_owner": owner_name})
    raise ServerTimeRequestError("이름 또는 PIN이 일치하지 않습니다.", code="owner_mismatch", status_code=403)


def record_audit(control, event_code, *, normal_estimate=None, detail=None):
    estimate = normal_estimate if normal_estimate is not None else normal_time_estimate(control)
    ServerTimeAudit.objects.create(
        event_code=event_code,
        owner_name=control.owner_name,
        requested_ip=control.requested_ip,
        revision=control.revision,
        observed_os_time=timezone.now(),
        normal_time_estimate=estimate,
        detail_json=detail or {},
    )
