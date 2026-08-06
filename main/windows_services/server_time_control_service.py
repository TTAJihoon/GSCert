import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")


try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError as exc:  # pragma: no cover - Windows deployment guard
    raise SystemExit("pywin32가 설치된 Windows 서버에서 실행해주세요.") from exc


class GSCertTimeControlService(win32serviceutil.ServiceFramework):
    _svc_name_ = "GSCertTimeControl"
    _svc_display_name_ = "GSCert Server Time Control"
    _svc_description_ = "Applies temporary GSCert server time changes and restores trusted time automatically."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        import django

        django.setup()
        from main.management.commands.run_server_time_agent import Command

        agent = Command()
        agent.dry_run = False
        servicemanager.LogInfoMsg("GSCertTimeControl started")
        try:
            agent._recover_interrupted_lease()
            while win32event.WaitForSingleObject(self.stop_event, 500) == win32event.WAIT_TIMEOUT:
                agent._tick()
        except Exception as exc:
            servicemanager.LogErrorMsg(f"GSCertTimeControl failed: {type(exc).__name__}")
            raise
        finally:
            from main.models import ServerTimeControl, ServerTimeControlStatus
            from main.server_time_control import get_control

            control = get_control()
            if control.status != ServerTimeControlStatus.IDLE:
                ServerTimeControl.objects.filter(id=1).update(
                    status=ServerTimeControlStatus.RESTORING,
                    pending_action="restore",
                )
                agent._restore(get_control(), event_code="service_stop_recovery")
            servicemanager.LogInfoMsg("GSCertTimeControl stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(GSCertTimeControlService)
