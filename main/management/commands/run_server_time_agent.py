import socket
import struct
import subprocess
import time
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F

from main.models import ServerTimeControl, ServerTimeControlStatus
from main.server_time_control import get_control, normal_time_estimate, record_audit, uptime_ms


NTP_EPOCH_OFFSET = 2_208_988_800


class Command(BaseCommand):
    help = "Run the privileged Windows agent that applies and restores temporary server time changes."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=0.5)

    def handle(self, *args, **options):
        if not options["dry_run"] and not hasattr(__import__("ctypes"), "windll"):
            raise CommandError("실제 서버 시간 변경 에이전트는 Windows에서만 실행할 수 있습니다.")
        self.dry_run = options["dry_run"]
        self.stdout.write("server-time agent started" + (" (dry-run)" if self.dry_run else ""))
        self._recover_interrupted_lease()
        while True:
            self._tick()
            if options["once"]:
                return
            time.sleep(max(0.1, options["poll_seconds"]))

    def _recover_interrupted_lease(self):
        control = get_control()
        if control.status in {
            ServerTimeControlStatus.ACTIVE,
            ServerTimeControlStatus.RESTORING,
            ServerTimeControlStatus.RECOVERY_FAILED,
        }:
            ServerTimeControl.objects.filter(id=1).update(
                status=ServerTimeControlStatus.RESTORING,
                pending_action="restore",
                error_message="",
            )
            self._restore(get_control(), event_code="agent_start_recovery")

    def _tick(self):
        current_uptime = uptime_ms()
        ServerTimeControl.objects.filter(id=1).update(agent_heartbeat_uptime_ms=current_uptime)
        control = get_control()
        if control.status == ServerTimeControlStatus.CHANGING:
            self._apply_change(control)
        elif control.status == ServerTimeControlStatus.RESTORING:
            self._restore(control, event_code="restore_completed")
        elif (
            control.status == ServerTimeControlStatus.ACTIVE
            and control.expires_uptime_ms is not None
            and current_uptime >= control.expires_uptime_ms
        ):
            updated = ServerTimeControl.objects.filter(
                id=1,
                status=ServerTimeControlStatus.ACTIVE,
                revision=control.revision,
            ).update(
                status=ServerTimeControlStatus.RESTORING,
                revision=F("revision") + 1,
                pending_action="restore",
            )
            if updated:
                self._restore(get_control(), event_code="automatic_restore_completed")

    def _apply_change(self, control):
        try:
            if control.target_time is None:
                raise RuntimeError("설정할 시간이 없습니다.")
            was_running = self._w32time_running()
            if was_running:
                self._stop_w32time()
            self._set_system_time(control.target_time.astimezone(datetime_timezone.utc))
            current_uptime = uptime_ms()
            lease_ms = int(getattr(settings, "SERVER_TIME_LEASE_SECONDS", 180) * 1000)
            ServerTimeControl.objects.filter(
                id=1,
                status=ServerTimeControlStatus.CHANGING,
                revision=control.revision,
            ).update(
                status=ServerTimeControlStatus.ACTIVE,
                pending_action="",
                w32time_was_running=was_running,
                expires_uptime_ms=current_uptime + lease_ms,
                error_message="",
            )
            updated = get_control()
            record_audit(updated, "time_changed", detail={"target_time": updated.target_time.isoformat()})
        except Exception as exc:
            self._mark_failed(control, "서버 시간 변경에 실패했습니다.", exc)

    def _restore(self, control, *, event_code):
        try:
            ntp_now = self._query_ntp()
            self._set_system_time(ntp_now)
            self._start_w32time()
            self._resync_w32time()
            verified_ntp = self._query_ntp()
            os_now = datetime.now(datetime_timezone.utc)
            tolerance = int(getattr(settings, "SERVER_TIME_VERIFY_TOLERANCE_SECONDS", 10))
            if abs((os_now - verified_ntp).total_seconds()) > tolerance:
                raise RuntimeError("정상 시간 원본과의 오차가 허용 범위를 벗어났습니다.")
            record_audit(control, event_code, normal_estimate=verified_ntp, detail={"ntp_host": self._ntp_host()})
            ServerTimeControl.objects.filter(id=1).update(
                status=ServerTimeControlStatus.IDLE,
                revision=F("revision") + 1,
                pending_action="",
                owner_name="",
                pin_hash="",
                requested_ip=None,
                target_time=None,
                normal_time_before_change=None,
                baseline_uptime_ms=None,
                expires_uptime_ms=None,
                failed_pin_attempts=0,
                last_pin_failure_uptime_ms=None,
                error_message="",
            )
        except Exception as exc:
            fallback = normal_time_estimate(control)
            if fallback is not None:
                try:
                    self._set_system_time(fallback.astimezone(datetime_timezone.utc))
                    self._start_w32time()
                except Exception:
                    pass
            self._mark_failed(control, "정상 시간 복구를 확인하지 못했습니다.", exc)

    def _mark_failed(self, control, public_message, exc):
        ServerTimeControl.objects.filter(id=1).update(
            status=ServerTimeControlStatus.RECOVERY_FAILED,
            pending_action="",
            error_message=public_message,
        )
        record_audit(get_control(), "agent_failed", detail={"error_type": type(exc).__name__})
        self.stderr.write(f"{public_message} ({type(exc).__name__})")

    def _ntp_host(self):
        return str(getattr(settings, "SERVER_TIME_NTP_HOST", "time.windows.com"))

    def _query_ntp(self):
        if self.dry_run:
            return datetime.now(datetime_timezone.utc)
        packet = b"\x1b" + 47 * b"\0"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(5)
            client.sendto(packet, (self._ntp_host(), 123))
            data, _ = client.recvfrom(512)
        if len(data) < 48:
            raise RuntimeError("NTP 응답이 올바르지 않습니다.")
        words = struct.unpack("!12I", data[:48])
        seconds = words[10] - NTP_EPOCH_OFFSET
        fraction = words[11] / 2**32
        return datetime.fromtimestamp(seconds + fraction, tz=datetime_timezone.utc)

    def _set_system_time(self, value):
        if self.dry_run:
            return
        import win32api

        utc_value = value.astimezone(datetime_timezone.utc)
        win32api.SetSystemTime(
            utc_value.year,
            utc_value.month,
            0,
            utc_value.day,
            utc_value.hour,
            utc_value.minute,
            utc_value.second,
            utc_value.microsecond // 1000,
        )

    def _w32time_running(self):
        if self.dry_run:
            return True
        import win32service

        manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        service = win32service.OpenService(manager, "W32Time", win32service.SERVICE_QUERY_STATUS)
        try:
            return win32service.QueryServiceStatus(service)[1] == win32service.SERVICE_RUNNING
        finally:
            win32service.CloseServiceHandle(service)
            win32service.CloseServiceHandle(manager)

    def _stop_w32time(self):
        if self.dry_run:
            return
        import win32service

        manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        service = win32service.OpenService(
            manager,
            "W32Time",
            win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS,
        )
        try:
            win32service.ControlService(service, win32service.SERVICE_CONTROL_STOP)
            self._wait_service(service, win32service.SERVICE_STOPPED)
        finally:
            win32service.CloseServiceHandle(service)
            win32service.CloseServiceHandle(manager)

    def _start_w32time(self):
        if self.dry_run:
            return
        import win32service

        manager = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        service = win32service.OpenService(
            manager,
            "W32Time",
            win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS,
        )
        try:
            status = win32service.QueryServiceStatus(service)[1]
            if status != win32service.SERVICE_RUNNING:
                win32service.StartService(service, None)
                self._wait_service(service, win32service.SERVICE_RUNNING)
        finally:
            win32service.CloseServiceHandle(service)
            win32service.CloseServiceHandle(manager)

    def _wait_service(self, service, wanted, timeout=15):
        import win32service

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if win32service.QueryServiceStatus(service)[1] == wanted:
                return
            time.sleep(0.2)
        raise RuntimeError("Windows Time 서비스 상태 변경이 제한 시간을 초과했습니다.")

    def _resync_w32time(self):
        if self.dry_run:
            return
        completed = subprocess.run(
            ["w32tm.exe", "/resync", "/force"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("Windows Time 강제 동기화에 실패했습니다.")
