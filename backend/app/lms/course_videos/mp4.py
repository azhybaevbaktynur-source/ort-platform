"""Pure-Python MP4 probe for lesson video uploads (LESSON_VIDEOS V2). No ffmpeg, no I/O.

Accepted: an ISO BMFF file whose FIRST box is `ftyp` with an MP4 brand (major or compatible), with a top-level `moov`
box (anywhere: "fast start" files have it first, plain exports at the end) holding `mvhd` and at least one video
track (`hdlr` = `vide`) whose sample entry is `avc1` (H.264). Every audio track (`soun`) must be `mp4a` (AAC); other
tracks (text, timecode) are ignored. Duration comes from `mvhd` (duration / timescale), width and height from the first
video track's `tkhd` (16.16 fixed point). 32-bit, 64-bit (`size == 1`) and to-end-of-file (`size == 0`) box sizes are
handled; every read is bounds-checked, and box nesting is limited, so a hostile file can only be refused (`Mp4Invalid`)."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, Optional

MP4_BRANDS = frozenset({
    b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"iso7", b"iso8", b"iso9",
    b"mp41", b"mp42", b"avc1", b"M4V ", b"M4VH", b"M4VP", b"dash", b"mmp4", b"msnv",
})
_MAX_TRACKS = 32


class Mp4Invalid(ValueError):
    """The bytes are not an MP4 this platform plays; `str(exc)` is a short reason (logged, never shown raw)."""


@dataclass(frozen=True)
class Mp4Info:
    duration_s: int
    width: int
    height: int
    has_audio: bool


def _boxes(buf: memoryview, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """(type, payload start, payload end) of the boxes in buf[start:end]."""
    pos = start
    while pos < end:
        if end - pos < 8:
            raise Mp4Invalid("truncated box header")
        size, kind = struct.unpack_from(">I4s", buf, pos)
        header = 8
        if size == 1:
            if end - pos < 16:
                raise Mp4Invalid("truncated large box header")
            (size,) = struct.unpack_from(">Q", buf, pos + 8)
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            raise Mp4Invalid(f"bad size of box {kind!r}")
        yield bytes(kind), pos + header, pos + size
        pos += size


def _child(buf: memoryview, start: int, end: int, kind: bytes) -> Optional[tuple[int, int]]:
    for k, s, e in _boxes(buf, start, end):
        if k == kind:
            return s, e
    return None


def _path(buf: memoryview, start: int, end: int, *kinds: bytes) -> Optional[tuple[int, int]]:
    span: Optional[tuple[int, int]] = (start, end)
    for kind in kinds:
        span = _child(buf, span[0], span[1], kind)
        if span is None:
            return None
    return span


def _need(s: int, e: int, n: int, what: str) -> None:
    if e - s < n:
        raise Mp4Invalid(f"truncated {what}")


def _mvhd(buf: memoryview, s: int, e: int) -> tuple[int, int]:
    """(timescale, duration)."""
    _need(s, e, 4, "mvhd")
    version = buf[s]
    if version == 1:
        _need(s, e, 4 + 8 + 8 + 4 + 8, "mvhd")
        timescale, duration = struct.unpack_from(">IQ", buf, s + 4 + 16)
    elif version == 0:
        _need(s, e, 4 + 4 + 4 + 4 + 4, "mvhd")
        timescale, duration = struct.unpack_from(">II", buf, s + 4 + 8)
    else:
        raise Mp4Invalid("unknown mvhd version")
    return timescale, duration


def _tkhd_size(buf: memoryview, s: int, e: int) -> tuple[int, int]:
    """(width, height) in whole pixels."""
    _need(s, e, 4, "tkhd")
    version = buf[s]
    if version == 1:
        off = 4 + 8 + 8 + 4 + 4 + 8
    elif version == 0:
        off = 4 + 4 + 4 + 4 + 4 + 4
    else:
        raise Mp4Invalid("unknown tkhd version")
    off += 8 + 2 + 2 + 2 + 2 + 36  # reserved, layer, alternate group, volume, reserved, matrix
    _need(s, e, off + 8, "tkhd")
    w, h = struct.unpack_from(">II", buf, s + off)
    return w >> 16, h >> 16


def _handler(buf: memoryview, mdia: tuple[int, int]) -> Optional[bytes]:
    span = _child(buf, mdia[0], mdia[1], b"hdlr")
    if span is None:
        return None
    _need(span[0], span[1], 12, "hdlr")
    return bytes(buf[span[0] + 8:span[0] + 12])


def _sample_entries(buf: memoryview, mdia: tuple[int, int]) -> list[bytes]:
    span = _path(buf, mdia[0], mdia[1], b"minf", b"stbl", b"stsd")
    if span is None:
        return []
    s, e = span
    _need(s, e, 8, "stsd")
    (count,) = struct.unpack_from(">I", buf, s + 4)
    out = []
    for kind, _ps, _pe in _boxes(buf, s + 8, e):
        out.append(kind)
        if len(out) >= min(count, _MAX_TRACKS):
            break
    return out


def probe(data: bytes) -> Mp4Info:
    """Validate and describe an MP4; raises `Mp4Invalid`."""
    buf = memoryview(data)
    top = _boxes(buf, 0, len(buf))
    try:
        first = next(top)
    except StopIteration:
        raise Mp4Invalid("empty file") from None
    kind, s, e = first
    if kind != b"ftyp":
        raise Mp4Invalid("ftyp is not the first box")
    _need(s, e, 8, "ftyp")
    brands = {bytes(buf[s:s + 4])} | {bytes(buf[i:i + 4]) for i in range(s + 8, e - 3, 4)}
    if not brands & MP4_BRANDS:
        raise Mp4Invalid("no MP4 brand")
    moov = None
    for kind, s, e in top:
        if kind == b"moov":
            moov = (s, e)
            break
    if moov is None:
        raise Mp4Invalid("no moov box")
    mvhd = _child(buf, moov[0], moov[1], b"mvhd")
    if mvhd is None:
        raise Mp4Invalid("no mvhd box")
    timescale, duration = _mvhd(buf, *mvhd)
    if timescale == 0:
        raise Mp4Invalid("zero timescale")
    duration_s = int((duration + timescale // 2) // timescale)
    if duration_s < 1:
        raise Mp4Invalid("no duration")
    size: Optional[tuple[int, int]] = None
    has_audio = False
    tracks = 0
    for kind, ts, te in _boxes(buf, moov[0], moov[1]):
        if kind != b"trak":
            continue
        tracks += 1
        if tracks > _MAX_TRACKS:
            raise Mp4Invalid("too many tracks")
        mdia = _child(buf, ts, te, b"mdia")
        if mdia is None:
            continue
        handler = _handler(buf, mdia)
        entries = _sample_entries(buf, mdia)
        if handler == b"vide":
            if not entries or any(x != b"avc1" for x in entries):
                raise Mp4Invalid("video is not H.264 (avc1)")
            if size is None:
                tkhd = _child(buf, ts, te, b"tkhd")
                if tkhd is None:
                    raise Mp4Invalid("no tkhd box")
                size = _tkhd_size(buf, *tkhd)
        elif handler == b"soun":
            if not entries or any(x != b"mp4a" for x in entries):
                raise Mp4Invalid("audio is not AAC (mp4a)")
            has_audio = True
    if size is None:
        raise Mp4Invalid("no video track")
    if size[0] <= 0 or size[1] <= 0:
        raise Mp4Invalid("no picture size")
    return Mp4Info(duration_s=duration_s, width=size[0], height=size[1], has_audio=has_audio)


__all__ = ["Mp4Info", "Mp4Invalid", "probe", "MP4_BRANDS"]
