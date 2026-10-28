"""Markdown render pipeline of pages and announcements (PHASE_8A_DESIGN 5.1, P8A-2).

`render(body_md) -> body_html`: `markdown` (extensions `extra, sane_lists, nl2br`) produces HTML, then `nh3` cleans it
with the allowlist of `pages/ids.py`. The sanitizer, not the Markdown library, is the trust boundary: raw HTML in the
source is allowed through Markdown and stripped by `nh3` (unknown tags lose their tag, `script`/`style`/`svg`/... lose
their content too; every attribute outside the allowlist is dropped).

URL rules (attribute filter): `a[href]` only `http`, `https`, `mailto` or a site-relative `/path` (never `//host`);
`img[src]` only our media route (`/api/v1/media/`) or `R2_PUBLIC_BASE_URL` (external and `data:` sources are
dropped); `code[class]` only `language-<name>`. Every link gets `rel="noopener noreferrer"`, absolute `http(s)` links
also `target="_blank"` (added after cleaning, a fixed attribute only).

Math: KaTeX is not rendered on the server. `$...$` and `$$...$$` are taken out before Markdown (so `_`, `*` and
line breaks inside a formula are not turned into emphasis or `<br>`) and put back as escaped text; the client runs
KaTeX auto-render on the text. Deterministic (a golden test fixes the output)."""
from __future__ import annotations

import html
import re
import uuid
from typing import Optional
from xml.etree.ElementTree import Element

import markdown
import nh3
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from app.core.config import settings
from app.lms.pages import ids

# Tags whose content is removed together with the tag (not only the tag, as for other unknown tags).
CLEAN_CONTENT_TAGS = frozenset({
    "script", "style", "svg", "math", "iframe", "object", "embed", "template", "noscript", "textarea", "select",
    "frame", "frameset", "noembed", "noframes", "xmp",
})
LINK_REL = "noopener noreferrer"
_CODE_CLASS_RE = re.compile(r"^language-[A-Za-z0-9_+#.-]{1,40}$")
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?![\s$])([^\n$]+?)(?<![\s\\])\$(?!\$)")
# nh3 output is normalized (attribute values double-quoted, `"` escaped inside them)
_A_TAG_RE = re.compile(r'<a\b((?:[^>"]|"[^"]*")*)>')
_HEADING_MAP = {"h1": "h2", "h5": "h4", "h6": "h4"}


class _HeadingLevels(Treeprocessor):
    """`#` becomes `h2` (the page title is the `h1`), `#####`/`######` become `h4`: the allowlist has h2-h4."""

    def run(self, root: Element) -> None:
        for el in root.iter():
            if el.tag in _HEADING_MAP:
                el.tag = _HEADING_MAP[el.tag]


class _HeadingExtension(Extension):
    def extendMarkdown(self, md) -> None:  # noqa: N802 (Markdown API)
        md.treeprocessors.register(_HeadingLevels(md), "lms_heading_levels", 1)


def _media_prefixes() -> tuple[str, ...]:
    out = [ids.MEDIA_PATH_PREFIX]
    base = (settings.R2_PUBLIC_BASE_URL or "").rstrip("/")
    if base.startswith("https://") or base.startswith("http://"):
        out.append(base + "/")
    return tuple(out)


def _href_ok(value: str) -> bool:
    v = value.strip()
    low = v.lower()
    if low.startswith(("http://", "https://", "mailto:")):
        return True
    return v.startswith("/") and not v.startswith("//") and "\\" not in v


def _src_ok(value: str) -> bool:
    v = value.strip()
    if "\\" in v or ".." in v:
        return False
    return v.startswith(_media_prefixes())


def _attribute_filter(tag: str, attr: str, value: str) -> Optional[str]:
    if tag == "a" and attr == "href":
        return value if _href_ok(value) else None
    if tag == "img" and attr == "src":
        return value if _src_ok(value) else None
    if tag == "code" and attr == "class":
        return value if _CODE_CLASS_RE.match(value) else None
    if tag == "a" and attr == "target":
        return None  # the server decides (external links only, below)
    return value


def _attributes() -> dict[str, set[str]]:
    # `rel` is forced by `link_rel` (nh3 refuses `rel` in both); `target` is set after cleaning
    return {tag: {a for a in attrs if a != "rel"} for tag, attrs in ids.ALLOWED_ATTRIBUTES.items()}


def _cleaner_kwargs() -> dict:
    return dict(
        tags=set(ids.ALLOWED_TAGS), clean_content_tags=set(CLEAN_CONTENT_TAGS), attributes=_attributes(),
        attribute_filter=_attribute_filter, strip_comments=True, link_rel=LINK_REL,
        url_schemes=set(ids.LINK_SCHEMES),
    )


def _stash_math(text: str) -> tuple[str, dict[str, str]]:
    token = uuid.uuid4().hex
    found: dict[str, str] = {}

    def keep(match: re.Match) -> str:
        key = f"M{token}{len(found)}E"
        found[key] = match.group(0)
        return key

    text = _DISPLAY_MATH_RE.sub(keep, text)
    text = _INLINE_MATH_RE.sub(keep, text)
    return text, found


def _restore_math(out: str, found: dict[str, str]) -> str:
    for key, src in found.items():
        out = out.replace(key, html.escape(src, quote=True))
    return out


def _external_targets(out: str) -> str:
    def add(match: re.Match) -> str:
        attrs = match.group(1)
        if re.search(r'\shref="https?://', attrs, re.IGNORECASE) and " target=" not in attrs:
            return f'<a{attrs} target="_blank">'
        return match.group(0)

    return _A_TAG_RE.sub(add, out)


def render(body_md: str) -> str:
    """Sanitized HTML of a Markdown source (pages and announcements). Never raises on content."""
    source, math = _stash_math(body_md or "")
    md = markdown.Markdown(extensions=[*ids.MARKDOWN_EXTENSIONS, _HeadingExtension()], output_format="html")
    raw = _restore_math(md.convert(source), math)
    clean = nh3.clean(raw, **_cleaner_kwargs())
    return _external_targets(clean).strip()


__all__ = ["render", "CLEAN_CONTENT_TAGS", "LINK_REL"]
