import socket
import struct
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
            remote_now = self._remote_now()
            tolerance = int(getattr(settings, "SERVER_TIME_VERIFY_TOLERANCE_SECONDS", 10))
            if abs((remote_now - verified_ntp).total_seconds()) > tolerance:
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
        record_audit(
            get_control(),
            "agent_failed",
            detail={"error_type": type(exc).__name__, "error_detail": str(exc)[:300]},
        )
        try:
            # Windows 서비스로 실행될 때는 콘솔이 없어 sys.stderr가 None이라
            # self.stderr.write()가 AttributeError를 던진다. 이 예외가 잡히지
            # 않으면 _tick() 전체가 죽어 서비스 프로세스가 크래시한다.
            self.stderr.write(f"{public_message} ({type(exc).__name__})")
        except Exception:
            pass

    def _ntp_host(self):
        return str(getattr(settings, "SERVER_TIME_NTP_HOST", "time.windows.com"))

    def _query_ntp(self):
        if self.dry_run:
            return datetime.now(datetime_timezone.utc)
        # UDP는 패킷 손실이 흔하고 재시도가 없으면 단 한 번의 유실로 전체 apply/restore가
        # 실패로 보고된다(85 쪽 실제 작업은 이미 끝났는데 확인만 실패하는 상황 재현됨).
        # 몇 번 재시도해 일시적 손실에 흔들리지 않게 한다.
        last_error = None
        attempts = 5
        for attempt in range(attempts):
            try:
                return self._query_ntp_once()
            except (OSError, RuntimeError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(2)
        raise last_error

    def _query_ntp_once(self):
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

    def _remote_session(self):
        import winrm

        host = getattr(settings, "SERVER_TIME_REMOTE_HOST", "")
        user = getattr(settings, "SERVER_TIME_REMOTE_USER", "")
        password = getattr(settings, "SERVER_TIME_REMOTE_PASSWORD", "")
        if not host or not user or not password:
            raise RuntimeError("원격 서버(85) 접속 정보(SERVER_TIME_REMOTE_*)가 설정되지 않았습니다.")
        # 실제 시간 변경은 아주 드물게(대부분 유휴 상태) 일어나므로 세션을 캐시해
        # 재사용하면 그 사이 연결이 끊겨 있다가 재사용 시점에 실패하는 경우가 있다.
        # 호출마다 새로 연결해 안정성을 우선한다.
        return winrm.Session(host, auth=(user, password), transport="ntlm")

    def _remote_ps(self, script):
        if self.dry_run:
            return ""
        # 여기서 실행하는 모든 스크립트(시간 설정/서비스 정지·시작/resync)는 몇 번을
        # 반복해도 결과가 같은 멱등 작업이라, 연결 자체가 간헐적으로 실패해도(85 쪽
        # 작업은 끝났는데 응답만 못 받는 경우 포함) 재시도가 안전하다. 특히 85의 OS
        # 시각을 실제로 몇 주씩 점프시키는 순간(Set-Date 실행 직후)에는 WinRM/원격
        # PowerShell 호스트 응답이 몇 초간 불안정해지는 경향이 있어 재시도 간격을
        # 넉넉히 둔다.
        last_error = None
        attempts = 5
        for attempt in range(attempts):
            try:
                result = self._remote_session().run_ps(script)
            except Exception as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(2)
                continue
            if result.status_code != 0:
                stderr = result.std_err.decode(errors="replace")
                last_error = RuntimeError(f"원격(85) 명령 실행 실패: {stderr[:300]}")
                if attempt < attempts - 1:
                    time.sleep(2)
                continue
            return result.std_out.decode(errors="replace")
        raise last_error

    def _remote_now(self):
        if self.dry_run:
            return datetime.now(datetime_timezone.utc)
        output = self._remote_ps("(Get-Date).ToUniversalTime().ToString('o')")
        return datetime.fromisoformat(output.strip())

    def _set_system_time(self, value):
        if self.dry_run:
            return
        # 85는 로컬 시간대(KST)로 시각을 받으므로 UTC 목표값을 그대로 넘기고
        # .NET의 ToLocalTime()이 85 자신의 시간대 설정을 기준으로 변환하게 한다.
        utc_value = value.astimezone(datetime_timezone.utc)
        script = (
            "$dt = [DateTime]::SpecifyKind([DateTime]::new("
            f"{utc_value.year},{utc_value.month},{utc_value.day},"
            f"{utc_value.hour},{utc_value.minute},{utc_value.second},{utc_value.microsecond // 1000}"
            "), [DateTimeKind]::Utc); "
            "Set-Date -Date $dt.ToLocalTime() | Out-Null"
        )
        self._remote_ps(script)

    def _w32time_running(self):
        if self.dry_run:
            return True
        output = self._remote_ps("(Get-Service -Name W32Time).Status")
        return output.strip() == "Running"

    def _stop_w32time(self):
        if self.dry_run:
            return
        self._remote_ps(
            "Stop-Service -Name W32Time -Force; "
            "$sw = [Diagnostics.Stopwatch]::StartNew(); "
            "while ((Get-Service -Name W32Time).Status -ne 'Stopped' -and $sw.Elapsed.TotalSeconds -lt 15) "
            "{ Start-Sleep -Milliseconds 200 }; "
            "if ((Get-Service -Name W32Time).Status -ne 'Stopped') { throw 'W32Time stop timeout' }"
        )

    def _start_w32time(self):
        if self.dry_run:
            return
        self._remote_ps(
            "if ((Get-Service -Name W32Time).Status -ne 'Running') { Start-Service -Name W32Time }; "
            "$sw = [Diagnostics.Stopwatch]::StartNew(); "
            "while ((Get-Service -Name W32Time).Status -ne 'Running' -and $sw.Elapsed.TotalSeconds -lt 15) "
            "{ Start-Sleep -Milliseconds 200 }; "
            "if ((Get-Service -Name W32Time).Status -ne 'Running') { throw 'W32Time start timeout' }"
        )

    def _resync_w32time(self):
        if self.dry_run:
            return
        self._remote_ps(
            "$p = Start-Process -FilePath w32tm.exe -ArgumentList '/resync','/force' "
            "-NoNewWindow -Wait -PassThru; "
            "if ($p.ExitCode -ne 0) { throw \"w32tm resync failed with exit code $($p.ExitCode)\" }"
        )
