"""Student UI U7 (STUDENT_UI_DESIGN 4.4): which `url` items are video lessons.

A `url` item whose address is an allowlisted YouTube or Vimeo video becomes `ItemStudentOut.video = {provider, id}`;
the frontend then embeds only `https://www.youtube-nocookie.com/embed/{id}` or `https://player.vimeo.com/video/{id}`
(never the stored URL), after the student taps play. Everything else stays a plain link.

Strict on purpose: `https` only, an exact host from the list (no suffix or prefix match), no user info, no port, no
backslashes, whitespace or control characters, one fixed path shape per host, and the id validated
(`[A-Za-z0-9_-]{11}` for YouTube, 1–12 digits for Vimeo). Pure function, no I/O.
"""
from __future__ import annotations

import re
from typing import Literal, Optional, TypedDict
from urllib.parse import parse_qs, urlsplit

Provider = Literal["youtube", "vimeo"]


class Video(TypedDict):
    provider: Provider
    id: str


_YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_VIMEO_ID = re.compile(r"[0-9]{1,12}")
_BAD_CHARS = re.compile(r"[\s\\\x00-\x1f\x7f]")

_YT_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"})
_YT_SHORT_HOSTS = frozenset({"youtu.be"})
_YT_NOCOOKIE_HOSTS = frozenset({"youtube-nocookie.com", "www.youtube-nocookie.com"})
_VIMEO_HOSTS = frozenset({"vimeo.com", "www.vimeo.com"})
_VIMEO_PLAYER_HOSTS = frozenset({"player.vimeo.com"})

URL_MAX = 2048


def _segments(path: str) -> list[str]:
    """`/embed/abc/` -> ["embed", "abc"]; an empty segment in the middle (`//`) makes the path invalid."""
    parts = path.split("/")
    if not parts or parts[0] != "":
        return []
    parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if any(p == "" for p in parts):
        return []
    return parts


def _yt(vid: str) -> Optional[Video]:
    return {"provider": "youtube", "id": vid} if _YT_ID.fullmatch(vid) else None


def _vimeo(vid: str) -> Optional[Video]:
    return {"provider": "vimeo", "id": vid} if _VIMEO_ID.fullmatch(vid) else None


def parse_video(url: Optional[str]) -> Optional[Video]:
    """`{provider, id}` for an allowlisted video URL, else None (the item stays a link)."""
    if not isinstance(url, str) or not url or len(url) > URL_MAX or _BAD_CHARS.search(url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or port is not None:
        return None
    netloc = parts.netloc
    if not netloc or "@" in netloc or ":" in netloc:
        return None
    host = netloc.lower()
    if parts.hostname is None or parts.hostname != host:
        return None
    seg = _segments(parts.path)

    if host in _YT_HOSTS:
        if seg == ["watch"]:
            values = parse_qs(parts.query, keep_blank_values=True).get("v") or []
            return _yt(values[0]) if len(values) == 1 else None
        if len(seg) == 2 and seg[0] in ("embed", "shorts"):
            return _yt(seg[1])
        return None
    if host in _YT_SHORT_HOSTS:
        return _yt(seg[0]) if len(seg) == 1 else None
    if host in _YT_NOCOOKIE_HOSTS:
        return _yt(seg[1]) if len(seg) == 2 and seg[0] == "embed" else None
    if host in _VIMEO_HOSTS:
        return _vimeo(seg[0]) if len(seg) == 1 else None
    if host in _VIMEO_PLAYER_HOSTS:
        return _vimeo(seg[1]) if len(seg) == 2 and seg[0] == "video" else None
    return None


__all__ = ["Video", "parse_video"]
