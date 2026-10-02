"""ECM 에 올라간 zip 을 통째로 내려받지 않고 내부 파일 목록·일부 파일만 읽는 도구.

zip 은 파일 끝에 목록(central directory)이 있어 임의 위치를 읽을 수 있다. ECM 의 /servlet/blob
이 HTTP Range 를 지원하면(206) 다음만 받는다.
  1) 파일 끝부분(EOCD + central directory) - 보통 수십 KB ~ 1MB
  2) 필요한 항목의 로컬 헤더 + 압축 데이터
그래서 수 GB 짜리 zip 이어도 시험성적서 1~2개 분량(수 MB)만 전송된다.

이 모듈의 EcmRangeFile 은 seek/read 가 되는 파일 객체라서 `zipfile.ZipFile(EcmRangeFile(...))` 로 바로 쓴다.
Range 미지원이면 첫 요청에서 EcmRangeUnsupported 가 나고 그 즉시 연결을 닫는다(전체 다운로드 없음).
"""

from __future__ import annotations

import io
import zipfile
from collections import OrderedDict

DEFAULT_BLOCK_SIZE = 256 * 1024
DEFAULT_MAX_BLOCKS = 16


class RangeBudgetExceeded(RuntimeError):
    """전송 한도(max_bytes)를 넘겨 읽으려 해서 중단한 경우(실수로 전체를 받는 것을 막는다)."""


class EcmRangeFile(io.RawIOBase):
    """ECM 파일 1개를 Range 요청으로 읽는 읽기 전용 seekable 파일 객체.

    - 블록 단위(기본 256KB)로 받아 LRU 캐시(최대 16블록)하므로 작은 읽기가 많아도 요청 수가 적다.
    - 전체 크기는 파일 목록 API 의 fileSize 를 쓴다(추가 HEAD 요청 없음).
    - requests / bytes_fetched 로 실제 전송량을 확인할 수 있다.
    """

    def __init__(self, client, file_meta, *, block_size=DEFAULT_BLOCK_SIZE, max_blocks=DEFAULT_MAX_BLOCKS, max_bytes=None):
        super().__init__()
        self._client = client
        self._meta = file_meta
        self.size = int(float(file_meta.get("fileSize") or 0))
        if self.size <= 0:
            raise ValueError("fileSize 를 알 수 없어 Range 로 읽을 수 없습니다.")
        self._block = int(block_size)
        self._max_blocks = int(max_blocks)
        self._max_bytes = max_bytes
        self._cache = OrderedDict()
        self._pos = 0
        self.requests = 0
        self.bytes_fetched = 0

    # ----- io 인터페이스 -----
    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self._pos + offset
        elif whence == io.SEEK_END:
            target = self.size + offset
        else:
            raise ValueError(f"invalid whence: {whence}")
        self._pos = max(0, target)
        return self._pos

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def read(self, size=-1):
        if self._pos >= self.size:
            return b""
        end = self.size if size is None or size < 0 else min(self.size, self._pos + size)
        out = bytearray()
        position = self._pos
        while position < end:
            index = position // self._block
            block = self._get_block(index)
            offset = position - index * self._block
            take = min(len(block) - offset, end - position)
            if take <= 0:
                break
            out += block[offset:offset + take]
            position += take
        self._pos = position
        return bytes(out)

    # ----- 내부 -----
    def _get_block(self, index):
        block = self._cache.get(index)
        if block is not None:
            self._cache.move_to_end(index)
            return block
        start = index * self._block
        end = min(self.size, start + self._block) - 1
        if self._max_bytes is not None and self.bytes_fetched + (end - start + 1) > self._max_bytes:
            raise RangeBudgetExceeded(
                f"전송 한도 {self._max_bytes:,} bytes 를 넘겨 중단합니다(이미 {self.bytes_fetched:,} bytes 받음)."
            )
        block = self._client.blob_range(self._meta, start, end)
        self.requests += 1
        self.bytes_fetched += len(block)
        self._cache[index] = block
        while len(self._cache) > self._max_blocks:
            self._cache.popitem(last=False)
        return block


def decoded_name(info):
    """zip 항목 이름을 올바른 한글로 복원한다.

    한국어 Windows 압축 도구는 UTF-8 플래그(0x800) 없이 CP949 로 이름을 저장하는 경우가 많다. Python 은 이를
    CP437 로 읽어 깨지므로, 플래그가 없으면 CP437 로 되돌린 바이트를 CP949 로 다시 해석한다.
    """
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def open_remote_zip(client, file_meta, **kwargs):
    """(ZipFile, EcmRangeFile) 를 돌려준다. ZipFile 생성 시 central directory 만 읽는다."""
    remote = EcmRangeFile(client, file_meta, **kwargs)
    return zipfile.ZipFile(remote), remote


def iter_entries(zf):
    """(디코딩된 전체 경로, ZipInfo) - 디렉터리 항목은 제외."""
    for info in zf.infolist():
        if info.is_dir():
            continue
        yield decoded_name(info), info
