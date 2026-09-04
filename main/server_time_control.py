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
        # GetTickCount64 반환값은 64비트이지만 ctypes 기본 restype(c_int, 32비트 signed)으로
        # 읽으면 값이 잘려 음수가 될 수 있어 명시적으로 c_uint64를 지정해야 한다.
        kernel32 = ctypes.windll.kernel32
        kernel32.GetTickCount64.restype = ctypes.c_uint64
        return int(kernel32.GetTickCount64())
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


def remote_time_estimate(control, *, current_uptime_ms=None):
    """ECM 서버(85)가 지금 보고 있을 시각 추정값. None이면 "확정할 수 없음"(적용 중)을 뜻한다.

    194 자신은 절대 바뀌지 않으므로 timezone.now()는 항상 194의 실제 시각만
    보여준다. lease가 active/restoring/recovery_failed인 동안은 85가 target_time
    에서부터 흘러온 가짜 시각을 표시 중이므로, 적용 시점(단조 uptime 기준)부터
    지난 시간을 target_time에 더해 85가 지금 보여줄 시각을 추정한다.

    changing 상태(최초 변경 또는 active 중 재설정으로 진입)는 애매하다 — 재설정이면
    target_time은 이미 새 값으로 바뀌었는데 expires_uptime_ms는 아직 이전 lease의
    값이라 그대로 계산하면 새 목표와 옛 기준시각이 뒤섞여 틀린 값이 나온다. 그렇다고
    무작정 194의 실제 시각을 보여주면, active 상태에서 재설정을 누른 짧은 순간
    "복귀됐다"고 착각하게 만든다(실제로 report된 버그). 그래서 changing 동안은
    아예 None을 돌려주고, 화면에서는 "적용 중" 같은 중립 표시로 넘긴다.
    """
    current_uptime_ms = current_uptime_ms if current_uptime_ms is not None else uptime_ms()
    if control.status == ServerTimeControlStatus.CHANGING:
        return None
    if (
        control.status not in {
            ServerTimeControlStatus.ACTIVE,
            ServerTimeControlStatus.RESTORING,
            ServerTimeControlStatus.RECOVERY_FAILED,
        }
        or control.target_time is None
        or control.expires_uptime_ms is None
    ):
        return timezone.now()
    lease_ms = int(getattr(settings, "SERVER_TIME_LEASE_SECONDS", 180) * 1000)
    applied_uptime_ms = control.expires_uptime_ms - lease_ms
    elapsed_ms = max(0, current_uptime_ms - applied_uptime_ms)
    return control.target_time + timedelta(milliseconds=elapsed_ms)


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
        "server_time": (
            estimate.isoformat()
            if (estimate := remote_time_estimate(control, current_uptime_ms=current_uptime)) is not None
            else None
        ),
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
