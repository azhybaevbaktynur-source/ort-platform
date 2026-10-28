"""Phase 8a S3: the Markdown render pipeline of pages and announcements (PHASE_8A_DESIGN 5.1, P8A-2).

The golden file fixes the exact output of a sample document and of every XSS vector; the property checks below make
the security intent explicit (a golden update that lets a vector through still fails here)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.config import settings
from app.lms.pages import render as render_mod
from app.lms.pages.render import render

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "page_render_golden.json"
CASES = json.loads(GOLDEN.read_text(encoding="utf-8"))

FORBIDDEN = (
    re.compile(r"<script", re.I), re.compile(r"\son[a-z]+\s*=", re.I), re.compile(r"javascript:", re.I),
    re.compile(r"vbscript:", re.I), re.compile(r"data:", re.I), re.compile(r"<svg", re.I),
    re.compile(r"<style", re.I), re.compile(r"style=", re.I), re.compile(r"<iframe", re.I),
    re.compile(r"<object", re.I), re.compile(r"<embed", re.I), re.compile(r"<form", re.I),
    re.compile(r"<input", re.I), re.compile(r"<!--"),
)
ALLOWED_TAGS = {"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "u", "s", "a", "img", "br", "hr",
                "blockquote", "code", "pre", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub"}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden(case):
    assert render(case["md"]) == case["html"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_no_vector_survives(case):
    out = case["html"]
    for rx in FORBIDDEN:
        assert not rx.search(out), (case["name"], rx.pattern, out)
    assert {t.lower() for t in re.findall(r"<([a-zA-Z0-9]+)", out)} <= ALLOWED_TAGS
    for src in re.findall(r'src="([^"]*)"', out):
        assert src.startswith("/api/v1/media/"), src
    for href in re.findall(r'href="([^"]*)"', out):
        if href.startswith("#"):
            assert re.fullmatch(r"#[A-Za-z0-9_:.-]+", href), href  # same-page fragment only
            continue
        assert href.startswith(("http://", "https://", "mailto:", "/")) and not href.startswith("//"), href
    for id_ in re.findall(r'\sid="([^"]*)"', out):
        assert re.fullmatch(r"fn(ref\d*)?:[A-Za-z0-9_-]+", id_), id_  # footnote anchors only


def test_every_link_is_noopener_and_external_opens_new_tab():
    out = render("[a](https://x.example) [b](/local) <a href='http://y.example' target='_self'>c</a>")
    links = re.findall(r"<a\b[^>]*>", out)
    assert len(links) == 3 and all('rel="noopener noreferrer"' in a for a in links)
    assert [('target="_blank"' in a) for a in links] == [True, False, True]


def test_katex_source_is_text_not_markup():
    md = "Solve $x_1 * x_2 = \\frac{a}{b}$ and $$\n\\int_0^1 f(x)\\,dx\n$$"
    out = render(md)
    assert "$x_1 * x_2 = \\frac{a}{b}$" in out  # no <em> from `_`/`*`
    assert "$$\n\\int_0^1 f(x)\\,dx\n$$" in out  # no <br> inside the display formula
    assert "<em>" not in out


def test_r2_public_images_allowed_other_hosts_dropped(monkeypatch):
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "https://cdn.example.org")
    out = render("![a](https://cdn.example.org/img/abc.webp) ![b](https://cdn.example.org.evil.com/x.webp) "
                 "![c](https://evil.example/img/abc.webp)")
    assert out.count("src=") == 1 and 'src="https://cdn.example.org/img/abc.webp"' in out
    monkeypatch.setattr(settings, "R2_PUBLIC_BASE_URL", "")
    assert "src=" not in render("![a](https://cdn.example.org/img/abc.webp)")


def test_media_path_traversal_dropped():
    assert "src=" not in render("![a](/api/v1/media/../../etc/passwd)")


def test_large_body_renders_and_is_deterministic():
    md = ("## Section\n\nSome *text* with $x^2$ and a [link](https://a.example).\n\n" * 1500)[:100_000]
    assert len(md) == 100_000
    first = render(md)
    assert first == render(md) and first.count("<h2>") >= 1000


def test_empty_and_whitespace():
    assert render("") == ""
    assert render("   \n\n ") == ""


def test_clean_content_tags_are_not_in_allowlist():
    assert not (render_mod.CLEAN_CONTENT_TAGS & ALLOWED_TAGS)


def test_footnote_fragments_link_to_their_anchors():
    """Phase 8a fix1 (L5): `#fragment` links survive (footnotes are no dead anchors); ids only as footnote anchors."""
    out = render("Claim[^1] and [below](#notes).\n\n[^1]: Source.")
    assert 'href="#fn:1"' in out and 'id="fn:1"' in out and 'href="#fnref:1"' in out and 'id="fnref:1"' in out
    assert 'href="#notes"' in out and 'target="_blank"' not in out
    for md in ("[x](#a/b)", "[x](<# x>)", "[x](#)", "<a href='#//evil.example'>x</a>", "<a href='#x\" y'>x</a>"):
        assert "href=" not in render(md), md
    assert "id=" not in render('<li id="location">l</li> <p id="fn:1">p</p> <sup id="fn:<b>">t</sup>')
