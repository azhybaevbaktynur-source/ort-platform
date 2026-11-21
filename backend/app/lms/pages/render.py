"""Markdown render pipeline of pages and announcements (PHASE_8A_DESIGN 5.1, P8A-2).

`render(body_md) -> body_html`: `markdown` (extensions `extra, sane_lists, nl2br`) produces HTML, then `nh3` cleans it
with the allowlist of `pages/ids.py`. The sanitizer, not the Markdown library, is the trust boundary: raw HTML in the
source is allowed through Markdown and stripped by `nh3` (unknown tags lose their tag, `script`/`style`/`svg`/... lose
their content too; every attribute outside the allowlist is dropped).

URL rules (attribute filter): `a[href]` only `http`, `https`, `mailto`, a site-relative `/path` (never `//host`) or a
same-page `#name` fragment (footnotes; `sup[id]`/`li[id]` keep only footnote ids `fn:...`/`fnref:...`);
`img[src]` only our media route (`/api/v1/media/`) or `R2_PUBLIC_BASE_URL` (external and `data:` sources are
dropped); `code[class]` only `language-<name>`. Every link gets `rel="noopener noreferrer"`, absolute `http(s)` links
also `target="_blank"` (added after cleaning, a fixed attribute only).

Math: KaTeX is not rendered on the server. `$...$` and `$$...$$` are taken out before Markdown (so `_`, `*` and
line breaks inside a formula are not turned into emphasis or `<br>`) and put back as escaped text; the client runs
KaTeX auto-render on the text. Deterministic (a golden test fixes the output).

Lesson components (LESSON_COURSE_REQUESTS C5): a treeprocessor (`_LessonComponents`, after inline parsing) turns
labelled blockquotes into callouts / self-checks / «Почему так?» / worked examples, a paragraph holding only a titled
image into a figure, and splits the body at top-level `<hr>` into `section.lesson-card` parts. Labels and classes live
in `ids.py`. Only the server creates these tags and classes: author HTML of the reserved tags loses its tags
(`_StripAuthorReserved`: raw HTML in the stash and `markdown="1"` elements), and every `class`/`role` token outside
`code` must carry a per-render nonce that only `_LessonComponents` writes, so author classes (raw HTML, `{: .x}`) are
dropped by the nh3 attribute filter."""
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
_FRAGMENT_RE = re.compile(r"^#[A-Za-z0-9_:.-]{1,80}$")
# `id` survives only as a Markdown footnote anchor (`fn:1`, `fnref:1`, `fnref2:1`) on `sup`/`li`: the targets of the
# `#fn:...` links. The fixed `fn` prefix with a colon cannot name a global or clobber a form field.
_FOOTNOTE_ID_RE = re.compile(r"^fn(?:ref\d*)?:[A-Za-z0-9_-]{1,40}$")


class _HeadingLevels(Treeprocessor):
    """`#` becomes `h2` (the page title is the `h1`), `#####`/`######` become `h4`: the allowlist has h2-h4."""

    def run(self, root: Element) -> None:
        for el in root.iter():
            if el.tag in _HEADING_MAP:
                el.tag = _HEADING_MAP[el.tag]


class _HeadingExtension(Extension):
    def extendMarkdown(self, md) -> None:  # noqa: N802 (Markdown API)
        md.treeprocessors.register(_HeadingLevels(md), "lms_heading_levels", 1)


# --- lesson components (C5) -------------------------------------------------------------------------------------------

_RESERVED_TAG_RE = re.compile(
    r"<(/?)(?:" + "|".join(sorted(ids.LESSON_RESERVED_TAGS)) + r")\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE,
)
# Raw author HTML of a reserved tag is renamed to this tag (attributes dropped): Markdown still treats the block as
# block-level, and nh3 strips it like any unknown tag, so the output equals what the old renderer gave for `<div>`.
_STRIPPED_TAG = "lms-stripped"


def _norm_label(text: str) -> str:
    return " ".join(text.strip(ids.LABEL_TRIM_CHARS).split()).casefold()


# normalized spelling -> (role, language, canonical label)
_LABELS: dict[str, tuple[str, str, str]] = {
    _norm_label(spelling): (role, lang, spellings[0])
    for role, langs in ids.LESSON_LABELS.items()
    for lang, spellings in langs.items()
    for spelling in spellings
}


_BLOCK_ROLES = frozenset(ids.CALLOUT_MODIFIERS) | {"why", "worked"}  # labels that start a component


def _leading_label(el: Element) -> Optional[tuple[str, str, str]]:
    """(role, language, canonical) when `el` is a paragraph starting with `<strong>LABEL</strong>`."""
    if el.tag != "p" or (el.text or "").strip() or not len(el):
        return None
    first = el[0]
    if first.tag != "strong" or len(first) or not first.text:
        return None
    return _LABELS.get(_norm_label(first.text))


def _drop_label(parent: Element, p: Element) -> None:
    """Remove the leading bold label (and a line break right after it); drop the paragraph when nothing is left."""
    strong = p[0]
    rest = (strong.tail or "").lstrip(ids.LABEL_TRIM_CHARS)
    p.remove(strong)
    if not rest and len(p) and p[0].tag == "br":
        br = p[0]
        rest = (br.tail or "").lstrip()
        p.remove(br)
    p.text = rest or None
    if not rest and not len(p):
        tail = p.tail
        idx = list(parent).index(p)
        parent.remove(p)
        if tail and tail.strip():  # never lose text (a blockquote child paragraph has no tail in practice)
            if idx:
                parent[idx - 1].tail = (parent[idx - 1].tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail


class _LessonComponents(Treeprocessor):
    """C5 items 1-6. Runs after inline parsing (20) and footnotes (15), before prettify (10) and attr_list (8)."""

    def __init__(self, md, nonce: str) -> None:
        super().__init__(md)
        self.nonce = nonce
        self.author_reserved: list[Element] = []

    def _cls(self, *names: str) -> str:
        return " ".join(self.nonce + n for n in names)

    def _label_p(self, text: str) -> Element:
        p = Element("p", {"class": self._cls("callout__label")})
        p.text = text
        return p

    def _make_callout(self, el: Element, role: str) -> None:
        el.tag = "aside"
        el.attrib.clear()
        el.set("class", self._cls("callout", ids.CALLOUT_MODIFIERS[role]))
        el.set("role", self.nonce + "note")

    def _summary(self, role: str, lang: str) -> Element:
        s = Element("summary")
        s.text = ids.LESSON_SUMMARY_TEXT[role][lang]
        return s

    def _blockquote(self, bq: Element) -> None:
        if not len(bq):
            return
        found = _leading_label(bq[0])
        if found is None:
            return
        role, lang, canonical = found
        if role in ids.CALLOUT_MODIFIERS:
            _drop_label(bq, bq[0])
            self._make_callout(bq, role)
            bq.insert(0, self._label_p(canonical))
            if role == "check":
                self._hide_answer(bq, lang)
        elif role == "why":
            _drop_label(bq, bq[0])
            bq.tag = "details"
            bq.attrib.clear()
            bq.set("class", self._cls("why"))
            bq.insert(0, self._summary("why", lang))
        elif role == "worked":
            _drop_label(bq, bq[0])
            bq.tag = "div"
            bq.attrib.clear()
            bq.set("class", self._cls("worked"))
            bq.insert(0, self._label_p(canonical))
            self._worked(bq)
        # `answer` (or any other role) as the first label: a plain blockquote

    def _hide_answer(self, aside: Element, lang: str) -> None:
        kids = list(aside)
        for i, el in enumerate(kids[1:], start=1):
            found = _leading_label(el)
            if found and found[0] == "answer":
                details = Element("details")
                details.append(self._summary("answer", lang))
                for k in kids[i:]:
                    aside.remove(k)
                    details.append(k)
                aside.append(details)
                return

    def _worked(self, box: Element) -> None:
        for idx, el in enumerate(list(box)):
            if el.tag == "ol":
                el.set("class", self._cls("worked__steps"))
                continue
            found = _leading_label(el)
            if found is None:
                continue
            if found[0] == "answer":
                el.set("class", self._cls("worked__answer"))
            elif found[0] == "trap":
                aside = Element("aside")
                self._make_callout(aside, "trap")
                aside.append(self._label_p(found[2]))
                aside.tail = el.tail
                el.tail = None
                box.remove(el)
                box.insert(idx, aside)
                aside.append(el)
                _drop_label(aside, el)

    def _figure(self, p: Element) -> None:
        if (p.text or "").strip() or len(p) != 1:
            return
        img = p[0]
        title = (img.get("title") or "").strip()
        if img.tag != "img" or (img.tail or "").strip() or not title:
            return
        p.tag = "figure"
        p.attrib.clear()
        p.text = None
        img.tail = None
        del img.attrib["title"]
        cap = Element("figcaption")
        cap.text = title
        p.append(cap)

    def _sections(self, root: Element) -> None:
        kids = list(root)
        trailing: list[Element] = []
        if kids and kids[-1].tag == "div" and "footnote" in (kids[-1].get("class") or "").split():
            trailing = [kids.pop()]  # footnotes stay after the cards
        if not any(k.tag == "hr" for k in kids):
            return
        for k in kids:
            root.remove(k)
        parts: list[list[Element]] = [[]]
        for k in kids:
            if k.tag == "hr":
                parts.append([])
            else:
                parts[-1].append(k)
        for part in parts:
            if not part:
                continue
            section = Element("section", {"class": self._cls("lesson-card")})
            section.extend(part)
            root.insert(len(root) - len(trailing), section)

    @staticmethod
    def _split_merged(bq: Element, parent: Element) -> list[Element]:
        """Markdown joins blockquotes separated only by a blank line (`> **Главное.** a` + `> **Приём.** b` is one
        blockquote). Split before every direct child paragraph that starts a component, except a `Ловушка` inside a
        `Разбор` (nested by C5)."""
        kids = list(bq)
        starts = [0]
        found = _leading_label(kids[0]) if kids else None
        group = found[0] if found else None
        for i in range(1, len(kids)):
            found = _leading_label(kids[i])
            role = found[0] if found else None
            if role in _BLOCK_ROLES and not (group == "worked" and role == "trap"):
                starts.append(i)
                group = role
        out = [bq]
        if len(starts) == 1:
            return out
        at = list(parent).index(bq)
        for n, (a, b) in enumerate(zip(starts[1:], [*starts[2:], len(kids)])):
            new = Element("blockquote")
            for k in kids[a:b]:
                bq.remove(k)
                new.append(k)
            parent.insert(at + 1 + n, new)
            out.append(new)
        return out

    def run(self, root: Element) -> None:
        self.author_reserved = [el for el in root.iter() if el is not root and el.tag in ids.LESSON_RESERVED_TAGS]
        parents = {c: p for p in root.iter() for c in p}
        for bq in reversed(list(root.iter("blockquote"))):  # inner blockquotes first
            for part in self._split_merged(bq, parents[bq]):
                self._blockquote(part)
        for p in list(root.iter("p")):
            self._figure(p)
        self._sections(root)


def _unwrap(el: Element, parent: Element) -> None:
    """Replace `el` by its text, children and tail (the string nh3 would leave after stripping the tag)."""
    idx = list(parent).index(el)
    children = list(el)
    parent.remove(el)

    def append_text(after: int, text: str) -> None:
        if not text:
            return
        if after < 0:
            parent.text = (parent.text or "") + text
        else:
            parent[after].tail = (parent[after].tail or "") + text

    append_text(idx - 1, el.text or "")
    for i, c in enumerate(children):
        parent.insert(idx + i, c)
    append_text(idx + len(children) - 1, el.tail or "")


def _strip_reserved_html(value):
    if isinstance(value, str):
        return _RESERVED_TAG_RE.sub(lambda m: f"<{m.group(1)}{_STRIPPED_TAG}>", value)
    for el in [e for e in value.iter() if e is not value and e.tag in ids.LESSON_RESERVED_TAGS][::-1]:
        parents = {c: p for p in value.iter() for c in p}
        _unwrap(el, parents[el])
    if value.tag in ids.LESSON_RESERVED_TAGS:
        value.tag = "p"  # rare (an extension stashing a reserved element): degrade to a paragraph, nh3 cleans it
        value.attrib.clear()
    return value


class _StripAuthorReserved(Treeprocessor):
    """Author HTML of the reserved tags never survives as tags: elements that existed before `_LessonComponents`
    (`markdown="1"` blocks, the footnotes `div`) are unwrapped, and the tags are removed from stashed raw HTML."""

    def __init__(self, md, components: _LessonComponents) -> None:
        super().__init__(md)
        self.components = components

    def run(self, root: Element) -> None:
        parents = {c: p for p in root.iter() for c in p}
        for el in reversed(self.components.author_reserved):  # descendants first
            parent = parents.get(el)
            if parent is not None:
                _unwrap(el, parent)
        blocks = self.md.htmlStash.rawHtmlBlocks
        for i, value in enumerate(blocks):
            blocks[i] = _strip_reserved_html(value)


class _LessonExtension(Extension):
    def __init__(self, nonce: str) -> None:
        super().__init__()
        self.nonce = nonce

    def extendMarkdown(self, md) -> None:  # noqa: N802 (Markdown API)
        md.block_level_elements.append(_STRIPPED_TAG)  # per-instance list
        components = _LessonComponents(md, self.nonce)
        md.treeprocessors.register(components, "lms_lesson_components", 12)
        md.treeprocessors.register(_StripAuthorReserved(md, components), "lms_strip_reserved", 4)


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
    if _FRAGMENT_RE.match(v):
        return True  # same-page anchor (footnotes): `#` + a plain name, nothing that could be a scheme or path
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
    if attr == "id":
        return value if _FOOTNOTE_ID_RE.match(value) else None
    if tag == "a" and attr == "target":
        return None  # the server decides (external links only, below)
    return value


def _attributes() -> dict[str, set[str]]:
    # `rel` is forced by `link_rel` (nh3 refuses `rel` in both); `target` is set after cleaning
    return {tag: {a for a in attrs if a != "rel"} for tag, attrs in ids.ALLOWED_ATTRIBUTES.items()}


def _server_tokens(value: str, nonce: str, allowed: frozenset[str]) -> Optional[str]:
    """`value` without the nonce when every token carries it and names an allowed value; otherwise None (dropped)."""
    out = []
    for token in value.split():
        name = token[len(nonce):] if token.startswith(nonce) else None
        if name not in allowed:
            return None
        out.append(name)
    return " ".join(out) or None


def _attribute_filter_for(nonce: str):
    def attribute_filter(tag: str, attr: str, value: str) -> Optional[str]:
        if attr == "class" and tag != "code":
            return _server_tokens(value, nonce, ids.LESSON_CLASSES)
        if attr == "role":
            return _server_tokens(value, nonce, ids.LESSON_ROLES) if tag == "aside" else None
        return _attribute_filter(tag, attr, value)

    return attribute_filter


def _cleaner_kwargs(nonce: str) -> dict:
    return dict(
        tags=set(ids.ALLOWED_TAGS), clean_content_tags=set(CLEAN_CONTENT_TAGS), attributes=_attributes(),
        attribute_filter=_attribute_filter_for(nonce), strip_comments=True, link_rel=LINK_REL,
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
    nonce = f"L{uuid.uuid4().hex}-"  # marks server-set classes and roles; removed by the attribute filter
    md = markdown.Markdown(
        extensions=[*ids.MARKDOWN_EXTENSIONS, _HeadingExtension(), _LessonExtension(nonce)], output_format="html",
    )
    raw = _restore_math(md.convert(source), math)
    clean = nh3.clean(raw, **_cleaner_kwargs(nonce))
    return _external_targets(clean).strip()


__all__ = ["render", "CLEAN_CONTENT_TAGS", "LINK_REL"]
