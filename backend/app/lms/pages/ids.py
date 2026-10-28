"""Stable names of the Phase 8a pages package (PHASE_8A_DESIGN 2.2, 5.1, 5.6). Pure constants: no DB, no app imports
beyond the shared 8a codes in `modules/ids.py`."""
from __future__ import annotations

from app.lms.modules.ids import (  # noqa: F401  (shared 8a codes, re-exported)
    E_HOME_PAGE_INVALID, E_LANGUAGE_NOT_IN_COURSE, E_MODULE_LOCKED, E_PAGE_CONFLICT, E_PAYLOAD_TOO_LARGE,
)

PAGE_TITLE_MAX = 300
PAGE_BODY_MAX = 100_000  # characters of body_md; above: 413 `payload_too_large` (preview: settings rate limit)

# Sanitizer allowlist (5.1; `pages/render.py`, S3). `nh3` is the trust boundary, not the Markdown library.
MARKDOWN_EXTENSIONS = ("extra", "sane_lists", "nl2br")
ALLOWED_TAGS = frozenset({
    "p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "u", "s", "a", "img", "br", "hr", "blockquote", "code",
    "pre", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub",
})
ALLOWED_ATTRIBUTES = {
    "a": frozenset({"href", "title", "rel", "target"}),
    "img": frozenset({"src", "alt", "title"}),
    "code": frozenset({"class"}),
}
LINK_SCHEMES = frozenset({"http", "https", "mailto"})  # plus relative `/` paths
MEDIA_PATH_PREFIX = "/api/v1/media/"                    # img.src: this prefix or settings.R2_PUBLIC_BASE_URL
