"""Stable names of the Phase 8a course files package (PHASE_8A_DESIGN 2.10, 5.3, 5.6). Pure constants."""
from __future__ import annotations

from app.lms.modules.ids import (  # noqa: F401  (shared 8a codes, re-exported)
    E_COURSE_FILES_QUOTA, E_MODULE_LOCKED, E_PAYLOAD_TOO_LARGE, E_STORAGE_FULL,
)

FILE_TITLE_MAX = 300
FOLDER_MAX = 200            # whole path, `/` separated
FOLDER_SEGMENT_MAX = 60     # each segment; no empty segment, no `.` or `..`
FOLDER_SEPARATOR = "/"
DOWNLOAD_URL_TTL_S = 120    # presigned GET on R2 (5.3)
UPLOAD_RATE_PER_HOUR = 30   # per user (route `+ratelimit`)

E_FOLDER_INVALID = "folder_invalid"  # 422
