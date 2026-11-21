"""Stable names of the lesson videos package (docs/phases/LESSON_VIDEOS.md V1-V3). Pure constants."""
from __future__ import annotations

VIDEO_MIME = "video/mp4"
VIDEO_EXT = "mp4"
CAPTIONS_MIME = "text/vtt"
CAPTIONS_EXT = "vtt"
CAPTIONS_MAX_BYTES = 200 * 1024     # PUT .../captions body (413 payload_too_large)
TITLE_MAX = 300
UPLOAD_RATE_PER_HOUR = 60           # per user (route `+ratelimit`)
PLAY_RATE_PER_HOUR = 600            # per user: /play and captions.vtt (per-user reads)
STREAM_CHUNK_MAX = 2 * 1024 * 1024  # dev stream: bytes per 206 answer (an open range is shortened, as HTTP allows)

E_VIDEO_INVALID = "video_invalid"            # 422: not an MP4 with H.264 video (+ AAC audio)
E_CAPTIONS_INVALID = "captions_invalid"      # 422: not UTF-8 WebVTT
E_VIDEO_IN_USE = "video_in_use"              # 409: a live module item points to it
E_VIDEO_NOT_FOUND = "video_not_found"        # 404
E_CAPTIONS_NOT_FOUND = "captions_not_found"  # 404: captions.vtt of a video without captions
E_ITEM_LOCKED = "item_locked"                # 403: module rule or Pro tier locks the item for the caller
E_TOKEN_INVALID = "video_token_invalid"      # 403: dev stream token bad, tampered or expired
E_RANGE = "range_not_satisfiable"            # 416
