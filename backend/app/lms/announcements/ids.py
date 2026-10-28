"""Stable names of the Phase 8a announcements package (PHASE_8A_DESIGN 2.11, 5.4, 5.6). Pure constants."""
from __future__ import annotations

from app.lms.modules.ids import E_ALREADY_PUBLISHED, E_PAGE_CONFLICT, E_PAYLOAD_TOO_LARGE  # noqa: F401

ANNOUNCEMENT_TITLE_MAX = 300
ANNOUNCEMENT_BODY_MAX = 20_000   # characters of body_md; above: 413 `payload_too_large`
HOME_ANNOUNCEMENTS_LIMIT = 3     # `/me/home` strip: latest three across the student's active courses
