"""ECM 에서 스트리밍으로 받는 zip 을 디스크에 저장하지 않고 순서대로 해석해 필요한 항목만 꺼낸다.

ECM `/servlet/blob` 은 Range 를 지원하지 않아 zip 일부만 받을 수 없다(2026-10-01 실측). 그래서 응답을
흘려받으면서 zip 의 '로컬 파일 헤더'를 처음부터 차례로 읽고,
  - 원하는 항목(예: 시험성적서 Word/PDF)만 메모리에 모아 압축을 풀고
  - 나머지 항목은 풀지도 저장하지도 않고 버린다.
전송은 zip 전체 크기만큼 일어나지만(194→ECM 약 41MB/s) 디스크 사용과 메모리 사용은 원하는 항목 크기뿐이다.

지원: stored/deflate, zip64, 데이터 디스크립터(deflate), CP949 이름(UTF-8 플래그 없음), CRC 검증.
지원 불가(ZipStreamUnsupported): 크기를 알 수 없는 stored+디스크립터, 비표준 압축 방식 등
→ 호출부가 임시 파일 방식(extract_via_tempfile)으로 대체한다. 암호화 항목은 건너뛰고 skipped 에 기록한다.
"""

from __future__ import annotations

import os
import struct
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field

LOCAL_SIG = b"PK\x03\x04"
CENTRAL_SIG = b"PK\x01\x02"
END_SIGS = (CENTRAL_SIG, b"PK\x05\x06", b"PK\x06\x06", b"PK\x06\x07", b"PK\x05\x05")
DESCRIPTOR_SIG = b"PK\x07\x08"
ZIP64_MAX = 0xFFFFFFFF
DEFAULT_MAX_ENTRY_BYTES = 256 * 1024 * 1024
INFLATE_STEP = 1 << 20


class ZipStreamUnsupported(Exception):
    """스트리밍 순차 해석으로는 처리할 수 없는 zip(호출부가 임시 파일 방식으로 대체)."""


class ZipStreamBudgetExceeded(Exception):
    """허용한 전송 한도를 넘겨 읽으려 해서 중단."""


@dataclass
class ExtractResult:
    files: list = field(default_factory=list)      # [(zip 안의 전체 경로, bytes)]
    skipped: list = field(default_factory=list)    # [(경로, 사유)]
    entries_seen: int = 0
    bytes_read: int = 0


def decode_name(raw: bytes, flag: int) -> str:
    """UTF-8 플래그가 있으면 UTF-8. 없으면 엄격한 UTF-8 을 먼저 시도하고(일부 도구는 플래그 없이 UTF-8 로 저장),
    아니면 CP949(한국어 Windows 압축 도구 기본), 그것도 안 되면 CP437 로 해석한다."""
    if flag & 0x800:
        return raw.decode("utf-8", errors="replace")
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp437", errors="replace")


class _ChunkReader:
    """청크 반복자 위에서 peek/read/skip 을 제공한다(필요한 만큼만 당겨 온다)."""

    def __init__(self, chunks, max_bytes=None):
        self._iterator = iter(chunks)
        self._buf = bytearray()
        self._max_bytes = max_bytes
        self.bytes_read = 0

    def _pull(self) -> bool:
        try:
            chunk = next(self._iterator)
        except StopIteration:
            return False
        self.bytes_read += len(chunk)
        if self._max_bytes is not None and self.bytes_read > self._max_bytes:
            raise ZipStreamBudgetExceeded(
                f"전송 한도 {self._max_bytes:,} bytes 를 넘겨 중단합니다."
            )
        self._buf += chunk
        return True

    def peek(self, n: int) -> bytes:
        while len(self._buf) < n and self._pull():
            pass
        return bytes(self._buf[:n])

    def read(self, n: int) -> bytes:
        while len(self._buf) < n:
            if not self._pull():
                raise EOFError("zip 스트림이 중간에 끝났습니다.")
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def skip(self, n: int) -> None:
        while n > 0:
            if not self._buf and not self._pull():
                raise EOFError("zip 스트림이 중간에 끝났습니다.")
            take = min(n, len(self._buf))
            del self._buf[:take]
            n -= take

    @property
    def position(self) -> int:
        """아직 소비하지 않은 다음 바이트의 스트림 안 위치(= 지금까지 파싱을 마친 바이트 수)."""
        return self.bytes_read - len(self._buf)

    def read_some(self, max_n: int) -> bytes:
        """버퍼에 있는 만큼(없으면 한 조각 더 받아서) 최대 max_n 바이트를 돌려준다. 스트림 끝이면 b""."""
        if not self._buf and not self._pull():
            return b""
        data = bytes(self._buf[:max_n])
        del self._buf[:max_n]
        return data

    def take_some(self) -> bytes:
        if not self._buf and not self._pull():
            return b""
        data = bytes(self._buf)
        self._buf.clear()
        return data

    def push_back(self, data: bytes) -> None:
        if data:
            self._buf[0:0] = data


def _zip64_sizes(extra: bytes, csize: int, usize: int):
    index = 0
    while index + 4 <= len(extra):
        header_id, size = struct.unpack("<HH", extra[index:index + 4])
        body = extra[index + 4:index + 4 + size]
        if header_id == 1:
            pos = 0
            if usize == ZIP64_MAX and pos + 8 <= len(body):
                usize = struct.unpack("<Q", body[pos:pos + 8])[0]
                pos += 8
            if csize == ZIP64_MAX and pos + 8 <= len(body):
                csize = struct.unpack("<Q", body[pos:pos + 8])[0]
            break
        index += 4 + size
    return csize, usize


def _read_descriptor(reader: _ChunkReader):
    """데이터 디스크립터를 읽어 (crc, csize, usize) 를 반환. 시그니처 유무·zip64 여부를 다음 시그니처로 판별한다."""
    head = reader.peek(32)
    starts = (LOCAL_SIG, CENTRAL_SIG) + END_SIGS
    for has_sig, wide in ((True, False), (True, True), (False, False), (False, True)):
        offset = 4 if has_sig else 0
        if has_sig and head[:4] != DESCRIPTOR_SIG:
            continue
        body = 4 + (16 if wide else 8)
        end = offset + body
        if len(head) >= end and (head[end:end + 4] in starts or len(head) == end):
            raw = reader.read(end)[offset:]
            crc = struct.unpack("<I", raw[:4])[0]
            if wide:
                csize, usize = struct.unpack("<QQ", raw[4:20])
            else:
                csize, usize = struct.unpack("<II", raw[4:12])
            return crc, csize, usize
    raise ZipStreamUnsupported("데이터 디스크립터 형식을 판별하지 못했습니다.")


def _inflate_known(method: int, raw: bytes) -> bytes:
    if method == 0:
        return raw
    if method == 8:
        return zlib.decompress(raw, -15)
    raise ZipStreamUnsupported(f"지원하지 않는 압축 방식({method})")


def extract_matching(chunks, want, *, max_entry_bytes=DEFAULT_MAX_ENTRY_BYTES, max_stream_bytes=None) -> ExtractResult:
    """chunks(bytes 조각 반복자)를 zip 으로 해석해 want(경로) 가 True 인 항목을 [(경로, bytes)] 로 꺼낸다."""
    reader = _ChunkReader(chunks, max_stream_bytes)
    result = ExtractResult()

    while True:
        signature = reader.peek(4)
        if signature != LOCAL_SIG:
            if signature == b"" or signature in END_SIGS:
                break
            raise ZipStreamUnsupported(f"예상하지 못한 zip 시그니처 {signature!r} (위치 약 {reader.bytes_read:,} bytes)")

        header = reader.read(30)
        _sig, _ver, flag, method, _mtime, _mdate, crc, csize, usize, name_len, extra_len = struct.unpack(
            "<4sHHHHHIIIHH", header
        )
        name = decode_name(reader.read(name_len), flag)
        extra = reader.read(extra_len)
        if csize == ZIP64_MAX or usize == ZIP64_MAX:
            csize, usize = _zip64_sizes(extra, csize, usize)

        result.entries_seen += 1
        is_dir = name.endswith("/") or name.endswith("\\")
        wanted = (not is_dir) and bool(want(name))
        if wanted and flag & 0x1:
            result.skipped.append((name, "암호화된 항목"))
            wanted = False

        if not flag & 0x8:
            # 크기를 헤더에서 알 수 있음 -> 원하지 않으면 읽지도 풀지도 않고 버린다.
            if wanted and csize > max_entry_bytes:
                result.skipped.append((name, f"항목이 너무 큼({csize:,} bytes)"))
                wanted = False
            if not wanted:
                reader.skip(csize)
                continue
            data = _inflate_known(method, reader.read(csize))
            if len(data) != usize or zlib.crc32(data) & 0xFFFFFFFF != crc:
                raise ZipStreamUnsupported(f"{name}: 크기/CRC 불일치(손상된 zip)")
            result.files.append((name, data))
            continue

        # 데이터 디스크립터 사용: 크기를 모르므로 deflate 스트림이 스스로 끝나는 지점까지 읽는다.
        if method != 8:
            raise ZipStreamUnsupported(f"{name}: 크기를 알 수 없는 방식(압축 {method} + 데이터 디스크립터)")
        inflater = zlib.decompressobj(-15)
        out = bytearray() if wanted else None
        while not inflater.eof:
            data = inflater.unconsumed_tail or reader.take_some()
            if not data:
                raise EOFError("zip 스트림이 중간에 끝났습니다.")
            produced = inflater.decompress(data, INFLATE_STEP)
            if out is not None:
                out += produced
                if len(out) > max_entry_bytes:
                    result.skipped.append((name, f"항목이 너무 큼(>{max_entry_bytes:,} bytes)"))
                    out = None
                    wanted = False
        reader.push_back(inflater.unused_data)
        desc_crc, _desc_csize, desc_usize = _read_descriptor(reader)
        if wanted and out is not None:
            if len(out) != desc_usize or zlib.crc32(bytes(out)) & 0xFFFFFFFF != desc_crc:
                raise ZipStreamUnsupported(f"{name}: 크기/CRC 불일치(손상된 zip)")
            result.files.append((name, bytes(out)))

    result.bytes_read = reader.bytes_read
    return result


def extract_via_tempfile(chunks, want, *, max_entry_bytes=DEFAULT_MAX_ENTRY_BYTES, max_stream_bytes=None, temp_dir=None) -> ExtractResult:
    """대체 경로: zip 을 임시 파일로 받은 뒤 zipfile 로 필요한 항목만 읽고 임시 파일을 즉시 삭제한다."""
    result = ExtractResult()
    handle, path = tempfile.mkstemp(prefix="kolas_zip_", suffix=".zip", dir=temp_dir)
    try:
        with os.fdopen(handle, "wb") as out:
            for chunk in chunks:
                result.bytes_read += len(chunk)
                if max_stream_bytes is not None and result.bytes_read > max_stream_bytes:
                    raise ZipStreamBudgetExceeded(f"전송 한도 {max_stream_bytes:,} bytes 를 넘겨 중단합니다.")
                out.write(chunk)
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                result.entries_seen += 1
                name = info.filename if info.flag_bits & 0x800 else _cp949_from_cp437(info.filename)
                if not want(name):
                    continue
                if info.flag_bits & 0x1:
                    result.skipped.append((name, "암호화된 항목"))
                elif info.file_size > max_entry_bytes:
                    result.skipped.append((name, f"항목이 너무 큼({info.file_size:,} bytes)"))
                else:
                    result.files.append((name, zf.read(info)))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return result


# ---------------------------------------------------------------------------
# 항목 단위 스트리밍 해석 (산출물 폴더 팝업: 목록 / 항목 1개 / 여러 항목 / 중첩 zip)
# ---------------------------------------------------------------------------
READ_STEP = 1 << 20
DEFAULT_MAX_ENTRIES = 200_000


def _inflate_pieces(inflater, data, step):
    """압축 해제 결과를 step 크기 이하 조각으로 나눠 내보낸다(작은 입력이 아주 큰 출력으로 불어나는 것 방지)."""
    out = inflater.decompress(data, step)
    if out:
        yield out
    while inflater.unconsumed_tail:
        out = inflater.decompress(inflater.unconsumed_tail, step)
        if out:
            yield out


class ZipEntry:
    """스트리밍 중인 zip 의 항목 1개.

    iter_data() 로 풀린 내용을 조금씩 받거나, 아무것도 안 하면 다음 항목으로 넘어갈 때 자동으로 건너뛴다.
    목록만 만들 때는 건너뛰는 동안 크기가 확정된다(size). 데이터 디스크립터를 쓰는 항목은 끝까지 읽어야 크기를 안다.
    """

    def __init__(self, reader, name, flag, method, crc, csize, usize):
        self._reader = reader
        self.name = name
        self.flag = flag
        self.method = method
        self.crc = crc
        self.compressed_size = csize
        self.has_descriptor = bool(flag & 0x8)
        self.size = None if self.has_descriptor else usize
        self.encrypted = bool(flag & 0x1)
        self.is_dir = name.endswith("/") or name.endswith("\\")
        self.done = False
        self.crc_ok = None
        self._started = False
        self.header_start = None  # 이 항목의 로컬 헤더가 시작되는 스트림 위치
        self.data_start = None    # 압축 데이터가 시작되는 스트림 위치

    def iter_data(self, chunk_size=READ_STEP):
        if self._started:
            raise RuntimeError("이미 읽거나 건너뛴 항목입니다.")
        self._started = True
        if self.encrypted:
            raise ZipStreamUnsupported(f"{self.name}: 암호화된 항목은 읽을 수 없습니다.")
        yield from self._consume(True, chunk_size)

    def skip(self):
        if self.done or self._started:
            return
        self._started = True
        for _ in self._consume(False, READ_STEP):
            pass

    def _consume(self, emit, chunk_size):
        reader = self._reader
        crc = 0
        total = 0
        if not self.has_descriptor:
            if not emit:
                reader.skip(self.compressed_size)
                self.done = True
                return
            if self.method not in (0, 8):
                raise ZipStreamUnsupported(f"{self.name}: 지원하지 않는 압축 방식({self.method})")
            inflater = zlib.decompressobj(-15) if self.method == 8 else None
            remaining = self.compressed_size
            while remaining > 0:
                piece = reader.read_some(min(remaining, chunk_size))
                if not piece:
                    raise EOFError("zip 스트림이 중간에 끝났습니다.")
                remaining -= len(piece)
                outputs = [piece] if inflater is None else _inflate_pieces(inflater, piece, chunk_size)
                for out in outputs:
                    total += len(out)
                    crc = zlib.crc32(out, crc)
                    yield out
            if inflater is not None:
                tail = inflater.flush()
                if tail:
                    total += len(tail)
                    crc = zlib.crc32(tail, crc)
                    yield tail
            self.size = total
            self.crc_ok = (crc & 0xFFFFFFFF) == self.crc
            self.done = True
            return

        # 데이터 디스크립터: 크기를 모르므로 deflate 스트림이 스스로 끝나는 곳까지 읽는다.
        if self.method != 8:
            raise ZipStreamUnsupported(f"{self.name}: 크기를 알 수 없는 방식(압축 {self.method} + 데이터 디스크립터)")
        inflater = zlib.decompressobj(-15)
        while not inflater.eof:
            data = reader.take_some()
            if not data:
                raise EOFError("zip 스트림이 중간에 끝났습니다.")
            try:
                for out in _inflate_pieces(inflater, data, chunk_size):
                    total += len(out)
                    crc = zlib.crc32(out, crc)
                    if emit:
                        yield out
            except zlib.error as exc:  # 암호화/손상된 데이터를 deflate 로 풀려다 실패
                raise ZipStreamUnsupported(f"{self.name}: 압축 데이터를 해석하지 못했습니다({exc})") from exc
        reader.push_back(inflater.unused_data)
        desc_crc, _csize, desc_usize = _read_descriptor(reader)
        self.size = desc_usize
        self.crc_ok = (crc & 0xFFFFFFFF) == desc_crc
        self.done = True


class ZipStream:
    """청크 반복자를 zip 으로 해석한다. entries() 가 ZipEntry 를 차례로 내놓는다."""

    def __init__(self, chunks, max_stream_bytes=None):
        self._reader = _ChunkReader(chunks, max_stream_bytes)

    @property
    def bytes_read(self):
        return self._reader.bytes_read

    @property
    def position(self):
        """지금까지 파싱을 마친 위치. 항목을 모두 읽고 나면 중앙 디렉터리가 시작되는 위치다."""
        return self._reader.position

    def entries(self):
        reader = self._reader
        while True:
            signature = reader.peek(4)
            if signature != LOCAL_SIG:
                if signature == b"" or signature in END_SIGS:
                    return
                raise ZipStreamUnsupported(
                    f"예상하지 못한 zip 시그니처 {signature!r} (위치 약 {reader.bytes_read:,} bytes)"
                )
            header_start = reader.position
            header = reader.read(30)
            _sig, _ver, flag, method, _mtime, _mdate, crc, csize, usize, name_len, extra_len = struct.unpack(
                "<4sHHHHHIIIHH", header
            )
            name = decode_name(reader.read(name_len), flag)
            extra = reader.read(extra_len)
            if csize == ZIP64_MAX or usize == ZIP64_MAX:
                csize, usize = _zip64_sizes(extra, csize, usize)
            entry = ZipEntry(reader, name, flag, method, crc, csize, usize)
            entry.header_start = header_start
            entry.data_start = reader.position
            yield entry
            entry.skip()


def iter_zip_entries(chunks, *, max_stream_bytes=None):
    return ZipStream(chunks, max_stream_bytes).entries()


def iter_entry_chunks(chunks, name, *, max_stream_bytes=None, chunk_size=READ_STEP):
    """name 항목의 풀린 내용을 조각으로 내보낸다. 항목을 다 내보내면 나머지 zip 은 읽지 않고 끝난다.

    항목이 없으면 KeyError. 중첩 zip 은 이 함수를 겹쳐서(바깥 zip 의 항목 -> 안쪽 zip 의 청크) 푼다.
    """
    for entry in iter_zip_entries(chunks, max_stream_bytes=max_stream_bytes):
        if entry.name == name and not entry.is_dir:
            yield from entry.iter_data(chunk_size)
            return
    raise KeyError(name)


def list_entries(chunks, *, max_stream_bytes=None, max_entries=DEFAULT_MAX_ENTRIES):
    """zip 의 항목 목록 [{name, size, compressed_size, is_dir, encrypted}] 과 읽은 바이트 수.

    항목 데이터는 풀지 않고 건너뛴다(데이터 디스크립터 항목만 크기를 알기 위해 풀어서 버린다).
    """
    stream = ZipStream(chunks, max_stream_bytes)
    entries = []
    for entry in stream.entries():
        entries.append(entry)
        if len(entries) > max_entries:
            raise ZipStreamBudgetExceeded(f"zip 항목이 {max_entries:,}개를 넘어 중단합니다.")
    return [
        {
            "name": entry.name,
            "size": entry.size,
            "compressed_size": entry.compressed_size,
            "is_dir": entry.is_dir,
            "encrypted": entry.encrypted,
        }
        for entry in entries
    ], stream.bytes_read


def iter_entry_from_file_range(path, data_start, method, compressed_size=None, *, chunk_size=READ_STEP):
    """파일 안의 data_start 위치에서 시작하는 항목 하나의 풀린 내용.

    zip 을 받으면서 기록해 둔 항목 위치(data_start)로, 아직 다 받지 못한 .part 파일에서도 이미 받아진 항목을 꺼낼 수 있다.
    deflate 는 스트림이 스스로 끝나므로 크기가 필요 없고, stored 는 compressed_size 가 필요하다.
    """
    if method not in (0, 8):
        raise ZipStreamUnsupported(f"지원하지 않는 압축 방식({method})")
    if method == 0 and compressed_size is None:
        raise ZipStreamUnsupported("크기를 알 수 없는 stored 항목")
    with open(path, "rb") as handle:
        handle.seek(data_start)
        if method == 0:
            remaining = compressed_size
            while remaining > 0:
                data = handle.read(min(remaining, chunk_size))
                if not data:
                    raise EOFError("파일이 중간에 끝났습니다.")
                remaining -= len(data)
                yield data
            return
        inflater = zlib.decompressobj(-15)
        while not inflater.eof:
            data = handle.read(chunk_size)
            if not data:
                raise EOFError("파일이 중간에 끝났습니다.")
            yield from _inflate_pieces(inflater, data, chunk_size)


def iter_file_chunks(path, *, chunk_size=READ_STEP):
    """파일 전체를 조각으로. (완성된 로컬 zip 을 네트워크 스트림처럼 해석기에 먹일 때 쓴다.)"""
    with open(path, "rb") as handle:
        while True:
            data = handle.read(chunk_size)
            if not data:
                return
            yield data


# ---- 순차 해석이 불가능한 zip 의 대체 경로(임시 파일) ----
def spool_to_tempfile(chunks, *, max_stream_bytes=None, temp_dir=None):
    """청크를 임시 파일로 받아 경로를 돌려준다. 호출자가 사용 후 지워야 한다."""
    handle, path = tempfile.mkstemp(prefix="gscert_zip_", suffix=".zip", dir=temp_dir)
    total = 0
    try:
        with os.fdopen(handle, "wb") as out:
            for chunk in chunks:
                total += len(chunk)
                if max_stream_bytes is not None and total > max_stream_bytes:
                    raise ZipStreamBudgetExceeded(f"전송 한도 {max_stream_bytes:,} bytes 를 넘겨 중단합니다.")
                out.write(chunk)
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    return path


def list_entries_from_file(path, *, max_entries=DEFAULT_MAX_ENTRIES):
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise ZipStreamBudgetExceeded(f"zip 항목이 {max_entries:,}개를 넘어 중단합니다.")
        result = []
        for info in infos:
            name = info.filename if info.flag_bits & 0x800 else _cp949_from_cp437(info.filename)
            result.append({
                "name": name,
                "size": info.file_size,
                "compressed_size": info.compress_size,
                "is_dir": info.is_dir(),
                "encrypted": bool(info.flag_bits & 0x1),
            })
    return result


def iter_file_entry_chunks(path, name, *, chunk_size=READ_STEP):
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            shown = info.filename if info.flag_bits & 0x800 else _cp949_from_cp437(info.filename)
            if shown == name and not info.is_dir():
                if info.flag_bits & 0x1:
                    raise ZipStreamUnsupported(f"{name}: 암호화된 항목은 읽을 수 없습니다.")
                with zf.open(info) as handle:
                    while True:
                        data = handle.read(chunk_size)
                        if not data:
                            return
                        yield data
        raise KeyError(name)


def _cp949_from_cp437(name: str) -> str:
    """zipfile 이 CP437 로 잘못 읽은 이름을 원래 바이트로 되돌려 decode_name 규칙으로 다시 해석한다."""
    try:
        return decode_name(name.encode("cp437"), 0)
    except UnicodeEncodeError:
        return name
