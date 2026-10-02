"""ECM zip 임시 보관(서버 디스크).

산출물 폴더 팝업에서 zip 을 열면 서버가 ECM 에서 zip 을 받으며 **목록 만들기와 사본 저장을 한 번의 전송으로** 한다.
사본이 완성되면 이후 목록 이동·파일 받기는 ECM 에 다시 접속하지 않고 이 사본에서 즉시 처리한다.
팝업을 열 때 root 폴더의 가장 큰 zip 1개는 미리 받기 시작한다(백그라운드).

- 같은 zip 은 한 번만 받는다(single-flight). 여러 사용자·탭이 같은 작업에 합류한다.
- 팝업(세션 id)이 그 zip 을 '보고 있는' 동안만 받기를 이어간다. 보는 팝업이 모두 닫히면(닫힘 신호 즉시, 신호가 끊기면 몇 초 뒤)
  85% 미만으로 받은 것은 곧바로 중단하고 지워 받기 자리를 다음 zip 에 넘긴다. 85% 이상이면 끝까지 받아 둔다.
- 받기 순서는 우선순위 큐다: 사용자가 실제로 연 zip(0) > 팝업을 열 때 미리 받기(1) > 다음 요청을 위한 사본 만들기(2).
- 용량 상한(LRU)과 매시 정각 초기화(정각 직전 유예 시간 안에 받은 것은 다음 정각까지 보관)를 지키고, 서버 재시작/수동 삭제 후에도 안전하게 복구한다.
  완성된 사본은 이름이 같고 크기가 ECM 의 fileSize 와 같을 때만 다시 쓴다.
- 이 폴더는 임시 저장소다. 비워도 된다(사용 중인 파일은 Windows 가 지우지 못하게 하므로 다음 번에 지워진다).
"""

import hashlib
import itertools
import logging
import os
import queue
import secrets
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = r"C:\Users\Administrator\zip_cache"
DEFAULT_MAX_GB = 50
DEFAULT_GRACE_MINUTES = 5
DEFAULT_WORKERS = 2
DEFAULT_MIN_FREE_BYTES = 512 * 1024 * 1024
ORPHAN_PART_SECONDS = 2 * 3600
SWEEP_INTERVAL_SECONDS = 60
LEASE_SECONDS = 10          # 팝업 신호(3초 간격)가 이 시간 끊기면 닫힌 것으로 본다(탭 강제 종료·네트워크 끊김 대비)
LEASE_CHECK_SECONDS = 2
NEAR_DONE_FRACTION = 0.85   # 이 이상 받았으면 보는 사람이 없어도 끝까지 받는다

RUNNING = "running"
COMPLETE = "complete"
FAILED = "failed"
CANCELED = "canceled"


class ZipSpoolCancelled(Exception):
    """보는 팝업이 없어져 받기를 중단했다."""

# 테스트에서 True 로 두면 받기 작업을 호출 스레드에서 바로 실행한다.
RUN_INLINE = False


def enabled():
    return bool(getattr(settings, "FOLDER_BROWSER_ZIP_CACHE", True))


def cache_dir():
    return Path(getattr(settings, "FOLDER_BROWSER_ZIP_CACHE_DIR", None) or DEFAULT_CACHE_DIR)


def max_bytes():
    return int(float(getattr(settings, "FOLDER_BROWSER_ZIP_CACHE_MAX_GB", DEFAULT_MAX_GB)) * 1024 ** 3)


def grace_seconds():
    return int(float(getattr(settings, "FOLDER_BROWSER_ZIP_CACHE_GRACE_MINUTES", DEFAULT_GRACE_MINUTES)) * 60)


def expires_at(completed_ts, grace=None):
    """사본이 지워지는 시각(epoch 초): 매 정각에 지우되, 정각 직전 grace 안에 받은 것은 다음 정각까지 남긴다.

    받은 시각 t 에 대해 '정각 B 가 t + grace 보다 늦은 첫 정각'이다.
    예) grace=5분: 2:30 에 받음 -> 3:00 삭제, 2:57 에 받음 -> 4:00 삭제.
    """
    grace = grace_seconds() if grace is None else grace
    shifted = time.localtime(completed_ts + grace)
    hour_start = time.mktime((shifted.tm_year, shifted.tm_mon, shifted.tm_mday, shifted.tm_hour, 0, 0, 0, 0, -1))
    return hour_start + 3600


def job_key(center, meta):
    """ECM 파일(센터 + 파일 ID + 크기)로 정한 키. 파일이 바뀌면(ID/크기 변경) 다른 키가 된다."""
    raw = f"{center}|{meta['storageFileID']}|{int(float(meta.get('fileSize') or 0))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@dataclass
class EntryRec:
    """받으면서 알게 된 zip 항목 하나. end 가 정해지고 end <= 받은 바이트 수이면 그 항목을 지금 꺼낼 수 있다."""

    name: str
    size: object          # 풀린 크기. 데이터 디스크립터 항목은 받은 뒤에야 안다.
    compressed_size: int
    is_dir: bool
    encrypted: bool
    method: int
    data_start: int
    end: object = None


class ZipJob:
    def __init__(self, key, center, meta, budget):
        self.key = key
        self.center = center
        self.meta = meta                      # ECM 파일 meta(fileName/fileOID/storageFileID/fileSize)
        self.budget = budget
        self.total = int(float(meta.get("fileSize") or 0))
        directory = cache_dir()
        self.part_path = directory / f"{key}.{secrets.token_hex(4)}.part"   # 작업마다 달라, 취소 직후 새로 시작해도 겹치지 않는다
        self.final_path = directory / f"{key}.zip"
        self.cond = threading.Condition()
        self.state = RUNNING
        self.written = 0
        self.error = None
        self.entries = []
        self.listing = None
        self.unsupported = False              # 순차 해석 불가 형식: 사본만 저장하고 목록은 완성 파일에서 만든다
        self.readers = 0
        self.created = time.monotonic()
        self.last_access = time.monotonic()
        self.completed_at = None              # 받기를 마친 시각(epoch 초). 매시 정각 초기화 판단 기준
        self.watchers = {}                    # 이 zip 을 보고 있는 팝업 {세션 id: 마지막 신호 시각}
        self.attached_once = False            # 한 번이라도 팝업이 붙었는지(붙은 적 없는 작업은 자동 취소하지 않는다)
        self.cancelled = False
        self.started = False                  # 받기 스레드가 시작했는지(대기열에서 기다리는 중이면 False)
        self.priority = 1
        self.target = None

    # ----- 상태 -----
    @property
    def data_path(self):
        return self.final_path if self.final_path.exists() else self.part_path

    def touch(self):
        self.last_access = time.monotonic()

    def progress(self):
        total = self.total or 1
        return {
            "state": self.state,
            "written": self.written,
            "total": self.total,
            "percent": 100 if self.state == COMPLETE else min(99, int(self.written * 100 / total)),
            "error": str(self.error) if self.error else "",
        }

    def wait(self, timeout):
        """완료/실패까지 기다린다. 반환: 최종 state(시간 초과면 RUNNING)."""
        deadline = time.monotonic() + timeout
        with self.cond:
            while self.state == RUNNING:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.cond.wait(min(remaining, 1.0))
            return self.state

    def find_ready_entry(self, name):
        """받는 중인 사본에서 지금 바로 꺼낼 수 있는 항목(끝까지 받아졌고 암호화되지 않은 stored/deflate)."""
        with self.cond:
            for rec in self.entries:
                if rec.name == name and not rec.is_dir and not rec.encrypted and rec.method in (0, 8):
                    if rec.end is not None and rec.end <= self.written:
                        return rec
                    return None
        return None

    @contextmanager
    def reading(self):
        """사본을 읽는 동안 용량 정리가 지우지 못하게 표시한다."""
        with self.cond:
            self.readers += 1
        try:
            self.touch()
            yield
        finally:
            with self.cond:
                self.readers -= 1

    def delete_files(self):
        paths = (self.part_path,) if self.cancelled else (self.final_path, self.part_path)
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.info("zip cache: could not delete %s (%s)", path, exc)
                return False
        return True


class ZipCache:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()
        self._queue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._worker_threads = []
        self._last_sweep = 0.0
        self._sweeper = None

    # ----- 조회 -----
    def lookup(self, center, meta):
        """키에 해당하는 작업(완성/진행 중)을 돌려준다. 파일이 사라졌거나 크기가 다르면 버린다. 없으면 None."""
        key = job_key(center, meta)
        with self._lock:
            self._sweep_locked()
            job = self._jobs.get(key)
            if job is not None and job.state == COMPLETE and not self._intact(job):
                self._jobs.pop(key, None)
                job = None
            if job is None:
                job = self._adopt(key, center, meta)
            if job is not None:
                job.touch()
            return job

    def _intact(self, job):
        try:
            return job.final_path.stat().st_size == job.total or job.part_path.stat().st_size == job.total
        except OSError:
            return False

    def _adopt(self, key, center, meta):
        """서버 재시작 뒤에도 남아 있는 완성 사본을 다시 쓴다(크기가 ECM 의 fileSize 와 같을 때만)."""
        job = ZipJob(key, center, meta, max_bytes())
        try:
            stat = job.final_path.stat()
            if stat.st_size != job.total or job.total <= 0:
                return None
        except OSError:
            return None
        job.completed_at = stat.st_mtime
        job.state = COMPLETE
        job.written = job.total
        job.listing = None   # 필요할 때 사본에서 만든다
        self._jobs[key] = job
        return job

    # ----- 시작 -----
    def ensure(self, center, meta, target, budget, sid=None, priority=1):
        """작업이 없으면 시작하고(백그라운드), 있으면 그것을 돌려준다. 보관을 쓸 수 없으면 None."""
        if not enabled():
            return None
        total = int(float(meta.get("fileSize") or 0))
        if total <= 0:
            return None
        existing = self.lookup(center, meta)
        if existing is not None and existing.state in (RUNNING, COMPLETE):
            with self._lock:
                self._attach_locked(existing, sid, priority)
            return existing

        with self._lock:
            key = job_key(center, meta)
            existing = self._jobs.get(key)
            if existing is not None and existing.state in (RUNNING, COMPLETE):
                self._attach_locked(existing, sid, priority)
                return existing
            self._sweep_locked()
            if not self._make_room_locked(total):
                logger.info("zip cache: no room for %s bytes", total)
                return None
            try:
                cache_dir().mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("zip cache: cannot create directory: %s", exc)
                return None
            job = ZipJob(key, center, meta, budget)
            job.target = target
            job.priority = priority
            self._jobs[key] = job
            self._attach_locked(job, sid, priority, queued=False)

        self._start_sweeper()
        self._submit(job)
        return job

    # ----- 보는 사람(팝업) 관리 -----
    def _attach_locked(self, job, sid, priority, queued=True):
        if sid:
            job.watchers[sid] = time.monotonic()
            job.attached_once = True
        if queued and job.state == RUNNING and not job.started and priority < job.priority:
            job.priority = priority  # 기다리던 미리 받기를 사용자가 직접 열면 대기열 앞으로 보낸다
            self._queue.put((priority, next(self._seq), job))

    def watch(self, sid):
        """팝업이 아직 열려 있다는 신호(약 3초마다)."""
        now = time.monotonic()
        with self._lock:
            for job in self._jobs.values():
                if sid in job.watchers:
                    job.watchers[sid] = now

    def release(self, sid):
        """팝업이 닫혔다는 신호. 보는 팝업이 더 없는 미완성 zip 은 받기를 중단한다."""
        with self._lock:
            for job in list(self._jobs.values()):
                if job.watchers.pop(sid, None) is not None:
                    self._cancel_if_unwatched_locked(job)

    def _expire_leases_locked(self, now):
        for job in list(self._jobs.values()):
            stale = [sid for sid, seen in job.watchers.items() if now - seen > LEASE_SECONDS]
            for sid in stale:
                job.watchers.pop(sid, None)
            if stale:
                self._cancel_if_unwatched_locked(job)

    def _cancel_if_unwatched_locked(self, job):
        if job.state != RUNNING or job.cancelled or job.watchers or not job.attached_once:
            return
        if job.total and job.written / job.total >= NEAR_DONE_FRACTION:
            return  # 거의 다 받았다: 끝까지 받아 둔다
        job.cancelled = True
        if self._jobs.get(job.key) is job:
            self._jobs.pop(job.key, None)  # 새 요청은 새 작업으로 시작한다
        with job.cond:
            job.state = CANCELED
            job.cond.notify_all()
        logger.info("zip cache: cancelled %s at %s/%s bytes (no popup is watching)",
                    job.meta.get("fileName"), job.written, job.total)
        if not job.started:
            job.delete_files()

    def _submit(self, job):
        if RUN_INLINE:
            job.started = True
            self._run(job.target, job)
            return
        workers = int(getattr(settings, "FOLDER_BROWSER_PREFETCH_WORKERS", DEFAULT_WORKERS))
        while len(self._worker_threads) < max(1, workers):
            thread = threading.Thread(
                target=self._worker_loop, name=f"zip-spool-{len(self._worker_threads)}", daemon=True,
            )
            self._worker_threads.append(thread)
            thread.start()
        self._queue.put((job.priority, next(self._seq), job))

    def _worker_loop(self):
        while True:
            _priority, _seq, job = self._queue.get()
            with self._lock:
                if job.started or job.state != RUNNING or job.cancelled:
                    continue  # 이미 시작했거나(우선순위 변경으로 중복 등록), 취소된 작업
                job.started = True
            self._run(job.target, job)

    def _run(self, target, job):
        try:
            target(job)
            if job.cancelled:
                job.delete_files()
                return
            job.completed_at = time.time()
            with job.cond:
                job.state = COMPLETE
                job.cond.notify_all()
        except BaseException as exc:  # 받기 실패(ECM 오류, 한도 초과 등)를 대기 중인 요청에 전달한다.
            if job.cancelled or isinstance(exc, ZipSpoolCancelled):
                job.cancelled = True
                job.delete_files()
                return
            logger.warning("zip cache: job failed for %s: %s", job.meta.get("fileName"), exc)
            with job.cond:
                job.error = exc
                job.state = FAILED
                job.cond.notify_all()
            job.delete_files()
            with self._lock:
                if self._jobs.get(job.key) is job:
                    self._jobs.pop(job.key, None)

    # ----- 디스크 관리 -----
    def _used_bytes_locked(self):
        used = 0
        for job in self._jobs.values():
            used += job.total
        return used

    def _make_room_locked(self, need):
        limit = max_bytes()
        if need > limit:
            return False
        directory = cache_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(directory).free
        except OSError:
            return False
        if free < need + DEFAULT_MIN_FREE_BYTES:
            return False
        used = self._used_bytes_locked()
        if used + need <= limit:
            return True
        victims = sorted(
            (job for job in self._jobs.values() if job.state == COMPLETE and job.readers == 0),
            key=lambda job: job.last_access,
        )
        for job in victims:
            if job.delete_files():
                self._jobs.pop(job.key, None)
                used -= job.total
                if used + need <= limit:
                    return True
        return used + need <= limit

    def _sweep_locked(self, now_wall=None):
        """매시 정각 초기화: 지워질 시각(expires_at)이 지난 사본과 주인 없는 임시 파일을 지운다(최대 1분에 한 번)."""
        now = time.monotonic()
        if now - self._last_sweep < SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        wall = time.time() if now_wall is None else now_wall
        for key, job in list(self._jobs.items()):
            if job.state != COMPLETE or job.readers:
                continue
            completed = job.completed_at if job.completed_at is not None else wall
            if wall >= expires_at(completed) and job.delete_files():
                self._jobs.pop(key, None)
        directory = cache_dir()
        try:
            names = list(directory.iterdir())
        except OSError:
            return
        known = {job.key for job in self._jobs.values()} | {job.part_path.stem for job in self._jobs.values()}
        for path in names:
            stem = path.stem
            if stem in known:
                continue
            try:
                mtime = path.stat().st_mtime
                if path.suffix == ".part" and wall - mtime > ORPHAN_PART_SECONDS:
                    path.unlink()
                elif path.suffix == ".zip" and wall >= expires_at(mtime):
                    path.unlink()
            except OSError:
                continue

    def _start_sweeper(self):
        """감시 스레드를 한 번 띄운다: 2초마다 팝업 신호(임대) 만료를 확인하고, 1분마다 정각 초기화를 확인한다."""
        if RUN_INLINE or self._sweeper is not None:
            return

        def loop():
            while True:
                time.sleep(LEASE_CHECK_SECONDS)
                try:
                    with self._lock:
                        self._expire_leases_locked(time.monotonic())
                        self._sweep_locked()
                except Exception:  # 감시 스레드는 어떤 경우에도 죽지 않는다.
                    logger.exception("zip cache: sweep failed")

        self._sweeper = threading.Thread(target=loop, name="zip-cache-sweeper", daemon=True)
        self._sweeper.start()

    def sweep(self, now_wall=None):
        with self._lock:
            self._last_sweep = 0.0
            self._sweep_locked(now_wall)

    def reset(self):
        """(테스트용) 등록된 작업을 모두 잊는다. 파일은 지우지 않는다."""
        with self._lock:
            self._jobs.clear()
            self._last_sweep = 0.0


zip_cache = ZipCache()
