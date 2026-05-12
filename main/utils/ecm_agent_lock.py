import asyncio
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from django.conf import settings

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import fcntl
except ImportError:
    fcntl = None


class EcmAgentLockTimeout(TimeoutError):
    pass


class EcmAgentLock:
    def __init__(self, path=None, timeout_seconds=None, poll_interval=0.2):
        self.path = Path(path or settings.ECM_AGENT_LOCK_PATH)
        self.timeout_seconds = timeout_seconds
        self.poll_interval = poll_interval
        self._file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b")
        self._ensure_lock_byte()

        started_at = time.monotonic()
        while True:
            try:
                self._lock_file()
                return self
            except OSError:
                if self.timeout_seconds is not None:
                    elapsed = time.monotonic() - started_at
                    if elapsed >= self.timeout_seconds:
                        self.release()
                        raise EcmAgentLockTimeout(
                            f"ECM agent lock wait exceeded {self.timeout_seconds} seconds"
                        )
                time.sleep(self.poll_interval)

    def release(self):
        if self._file is None:
            return
        try:
            self._unlock_file()
        finally:
            self._file.close()
            self._file = None

    def _ensure_lock_byte(self):
        self._file.seek(0)
        if self._file.read(1) == b"":
            self._file.seek(0)
            self._file.write(b"\0")
            self._file.flush()
        self._file.seek(0)

    def _lock_file(self):
        self._file.seek(0)
        if msvcrt is not None:
            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        if fcntl is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        raise RuntimeError("No supported file locking backend is available")

    def _unlock_file(self):
        self._file.seek(0)
        if msvcrt is not None:
            try:
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        if fcntl is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)


@contextmanager
def ecm_agent_lock(path=None, timeout_seconds=None, poll_interval=0.2):
    lock = EcmAgentLock(path, timeout_seconds, poll_interval)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


@asynccontextmanager
async def async_ecm_agent_lock(path=None, timeout_seconds=None, poll_interval=0.2):
    lock = EcmAgentLock(path, timeout_seconds, poll_interval)
    await asyncio.to_thread(lock.acquire)
    try:
        yield lock
    finally:
        await asyncio.to_thread(lock.release)
