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
# Lesson component tags (LESSON_COURSE_REQUESTS C5): only the server creates them. Author HTML of these tags (raw or
# via `markdown="1"`) loses its tags before the output is assembled (render._LessonComponents).
LESSON_RESERVED_TAGS = frozenset({"section", "aside", "figure", "figcaption", "details", "summary", "div"})
ALLOWED_TAGS = frozenset({
    "p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "u", "s", "a", "img", "br", "hr", "blockquote", "code",
    "pre", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub",
}) | LESSON_RESERVED_TAGS
ALLOWED_ATTRIBUTES = {
    "a": frozenset({"href", "title", "rel", "target"}),
    "img": frozenset({"src", "alt", "title"}),
    "code": frozenset({"class"}),
    "sup": frozenset({"id"}),  # footnote anchors only (render._FOOTNOTE_ID_RE)
    "li": frozenset({"id"}),
    # lesson components: `class` only with LESSON_CLASSES values, `role` only `note` on `aside`, and only when the
    # server set them (render: per-render nonce); author classes are always dropped
    "section": frozenset({"class"}),
    "aside": frozenset({"class", "role"}),
    "p": frozenset({"class"}),
    "ol": frozenset({"class"}),
    "div": frozenset({"class"}),
    "details": frozenset({"class"}),
}
LINK_SCHEMES = frozenset({"http", "https", "mailto"})  # plus relative `/` paths
MEDIA_PATH_PREFIX = "/api/v1/media/"                    # img.src: this prefix or settings.R2_PUBLIC_BASE_URL

# Lesson components (LESSON_COURSE_REQUESTS C5, content studio R6). Authors write plain Markdown; a blockquote whose
# first paragraph starts with a bold label becomes a component. Edit the labels here.
LESSON_CLASSES = frozenset({
    "lesson-card", "callout", "callout--key", "callout--tip", "callout--trap", "callout--recall", "callout--check",
    "callout__label", "why", "worked", "worked__steps", "worked__answer",
})
LESSON_ROLES = frozenset({"note"})  # `role` values, on `aside` only
LABEL_TRIM_CHARS = " \t\n .:?!"  # trimmed from both ends of a label before matching (case-insensitive)
# role -> language -> accepted spellings; the first spelling is the canonical label shown on the page.
# Kyrgyz labels: pending a native speaker check (content studio `ky_review`).
LESSON_LABELS: dict[str, dict[str, tuple[str, ...]]] = {
    "key": {"ru": ("Главное",), "ky": ("Негизгиси",)},
    "tip": {"ru": ("Приём", "Прием"), "ky": ("Ыкма",)},
    "trap": {"ru": ("Ловушка",), "ky": ("Тузак",)},
    "recall": {"ru": ("Вспомни",), "ky": ("Эсиңе түшүр",)},
    "check": {"ru": ("Проверь себя",), "ky": ("Өзүңдү текшер",)},
    "answer": {"ru": ("Ответ",), "ky": ("Жообу",)},
    "why": {"ru": ("Почему так",), "ky": ("Эмне үчүн",)},
    "worked": {"ru": ("Разбор",), "ky": ("Талдоо",)},
}
# label role -> modifier class of `aside.callout`
CALLOUT_MODIFIERS = {
    "key": "callout--key", "tip": "callout--tip", "trap": "callout--trap", "recall": "callout--recall",
    "check": "callout--check",
}
# `<summary>` text by the label's language (ky pending a native check)
LESSON_SUMMARY_TEXT: dict[str, dict[str, str]] = {
    "answer": {"ru": "Показать ответ", "ky": "Жоопту көрсөт"},
    "why": {"ru": "Почему так?", "ky": "Эмне үчүн?"},
}
