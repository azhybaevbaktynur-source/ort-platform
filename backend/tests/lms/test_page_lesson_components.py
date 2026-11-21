"""Lesson components of the page renderer (LESSON_COURSE_REQUESTS C5, content studio R6 F1/F3).

Authors write plain Markdown; `pages/render.py` turns labelled blockquotes, titled images and top-level `---` into
semantic HTML with a fixed class allowlist. Only the server creates the reserved tags and classes."""
from __future__ import annotations

import re

import pytest

from app.lms.pages import ids
from app.lms.pages.render import render

RU = """## Дроби

Вступление с $a_1$.

> **Главное.** Дробь — это $\\frac{a}{b}$.

> **Приём:** Сокращай.

---

> **Ловушка.**
> Не делите на ноль.

> **Вспомни.** Числитель сверху.

> **Проверь себя.** Сколько будет $1/2 + 1/2$?
>
> **Ответ.** $1$.
>
> Потому что так.

> **Почему так?** Потому что $x_1 * x_2$.

---

> **Разбор.** Найдите $x$.
>
> 1. Шаг один.
> 2. Шаг два.
>
> **Ответ:** $x = 2$.
>
> **Ловушка.** Знак.

![Схема](/api/v1/media/abc.webp "Подпись к схеме")
"""

RU_HTML = """<section class="lesson-card">
<h2>Дроби</h2>
<p>Вступление с $a_1$.</p>
<aside class="callout callout--key" role="note">
<p class="callout__label">Главное</p>
<p>Дробь — это $\\frac{a}{b}$.</p>
</aside>
<aside class="callout callout--tip" role="note">
<p class="callout__label">Приём</p>
<p>Сокращай.</p>
</aside>
</section>
<section class="lesson-card">
<aside class="callout callout--trap" role="note">
<p class="callout__label">Ловушка</p>
<p>Не делите на ноль.</p>
</aside>
<aside class="callout callout--recall" role="note">
<p class="callout__label">Вспомни</p>
<p>Числитель сверху.</p>
</aside>
<aside class="callout callout--check" role="note">
<p class="callout__label">Проверь себя</p>
<p>Сколько будет $1/2 + 1/2$?</p>
<details>
<summary>Показать ответ</summary>
<p><strong>Ответ.</strong> $1$.</p>
<p>Потому что так.</p>
</details>
</aside>
<details class="why">
<summary>Почему так?</summary>
<p>Потому что $x_1 * x_2$.</p>
</details>
</section>
<section class="lesson-card">
<div class="worked">
<p class="callout__label">Разбор</p>
<p>Найдите $x$.</p>
<ol class="worked__steps">
<li>Шаг один.</li>
<li>Шаг два.</li>
</ol>
<p class="worked__answer"><strong>Ответ:</strong> $x = 2$.</p>
<aside class="callout callout--trap" role="note">
<p class="callout__label">Ловушка</p>
<p>Знак.</p>
</aside>
</div>
<figure><img alt="Схема" src="/api/v1/media/abc.webp"><figcaption>Подпись к схеме</figcaption>
</figure>
</section>"""

KY = (RU.replace("Главное", "Негизгиси").replace("Приём", "Ыкма").replace("Ловушка", "Тузак")
      .replace("Вспомни", "Эсиңе түшүр").replace("Проверь себя", "Өзүңдү текшер").replace("Ответ", "Жообу")
      .replace("Почему так", "Эмне үчүн").replace("Разбор", "Талдоо"))


def _classes(out: str) -> list[str]:
    return [c for value in re.findall(r'class="([^"]*)"', out) for c in value.split()]


def test_all_components_ru():
    out = render(RU)
    assert out == RU_HTML
    assert out == render(RU)  # deterministic (the nonce never reaches the output)
    assert set(_classes(out)) <= ids.LESSON_CLASSES


def test_all_components_ky():
    out = render(KY)
    assert "<summary>Жоопту көрсөт</summary>" in out and "<summary>Эмне үчүн?</summary>" in out
    for label in ("Негизгиси", "Ыкма", "Тузак", "Эсиңе түшүр", "Өзүңдү текшер", "Талдоо"):
        assert f'<p class="callout__label">{label}</p>' in out, label
    assert out.count("<section ") == 3 and '<div class="worked">' in out and '<details class="why">' in out
    assert '<p class="worked__answer"><strong>Жообу:</strong> $x = 2$.</p>' in out
    # the same structure as ru: only the label texts differ
    assert re.sub(r">[^<]*<", "><", out) == re.sub(r">[^<]*<", "><", RU_HTML)


@pytest.mark.parametrize("md", [
    "<details open><summary>s</summary>secret</details>",
    '<aside class="callout callout--key" role="note">x</aside>',
    '<section class="lesson-card">x</section>',
    '<figure><figcaption>c</figcaption></figure>',
    '<div class="worked">x</div>',
    '<div markdown="1" class="worked">\n*z*\n</div>',
    '<details markdown="1">\n<summary>s</summary>\n\n*z*\n</details>',
    'text <aside>inline</aside> <details>d</details>',
    '<p class="callout__label">y</p>',
    '<blockquote class="callout" role="note">q</blockquote>',
    "hi\n{: .callout }",
    "> **Главное.** x\n{: .evil }",
])
def test_author_html_and_classes_are_stripped(md):
    out = render(md)
    for tag in ids.LESSON_RESERVED_TAGS - {"aside"}:
        assert f"<{tag}" not in out, (md, out)
    if "Главное" not in md:
        assert "<aside" not in out, (md, out)
    assert "lms-stripped" not in out
    assert ' role="' not in out or out.count(' role="note"') == out.count("<aside")
    for value in re.findall(r'class="([^"]*)"', out):
        assert value != "callout__label" or "Главное" in md


def test_author_raw_tags_keep_text_and_old_output():
    assert render("<div onmouseover=alert(1)>hover</div>") == "hover"
    assert render("<details><summary>s</summary>secret</details>") == "ssecret"
    out = render('<p class="callout__label">y</p>\n\n<aside class="callout">x</aside>')
    assert out == "<p>y</p>\n\nx"
    # attr_list class on a server callout: the whole class is dropped, never an author token
    out = render("> **Главное.** x\n{: .evil }")
    assert "evil" not in out and "<aside" in out


def test_code_is_not_touched():
    out = render("`<aside>` and\n\n```\n<details class=\"why\">\n```")
    assert "<code>&lt;aside&gt;</code>" in out and "&lt;details class=\"why\"&gt;" in out


def test_unknown_label_stays_blockquote():
    out = render("> **Неизвестно.** Обычная цитата.")
    assert out == "<blockquote>\n<p><strong>Неизвестно.</strong> Обычная цитата.</p>\n</blockquote>"
    assert render("> Просто **Главное.** в середине") .startswith("<blockquote>")
    assert render("> **Ответ.** без вопроса").startswith("<blockquote>")


@pytest.mark.parametrize("label", ["ГЛАВНОЕ", "главное!", "Главное :", "Главное?!", "главное."])
def test_label_case_insensitive_and_trimmed(label):
    out = render(f"> **{label}** текст")
    assert out.startswith('<aside class="callout callout--key" role="note">\n<p class="callout__label">Главное</p>')
    assert "<p>текст</p>" in out


def test_label_variants_and_tail_punctuation():
    assert '<p class="callout__label">Приём</p>' in render("> **Прием** текст")
    out = render("> **Главное**: текст")
    assert "<p>текст</p>" in out
    assert '<p class="callout__label">Эсиңе түшүр</p>' in render("> **эсиңе  түшүр.** текст")


def test_hr_without_components_yields_sections():
    out = render("one\n\n---\n\ntwo\n\n***\n\nthree")
    assert out == ('<section class="lesson-card">\n<p>one</p>\n</section>\n<section class="lesson-card">\n'
                   '<p>two</p>\n</section>\n<section class="lesson-card">\n<p>three</p>\n</section>')
    assert "<hr>" not in out
    assert render("---\n\nonly\n\n---") == '<section class="lesson-card">\n<p>only</p>\n</section>'


def test_no_hr_no_sections_and_footnotes_stay_outside():
    assert "<section" not in render("one\n\ntwo")
    out = render("a[^1]\n\n---\n\nb\n\n[^1]: Note.")
    assert out.count("<section") == 2 and out.index("</section>\n\n<hr>") > 0
    assert 'id="fn:1"' in out and out.rindex("</section>") < out.index('id="fn:1"')
    assert "<section" not in render("Claim[^1].\n\n[^1]: Source.")


def test_math_inside_callout_and_details_survives_escaped():
    md = ("> **Главное.** $a<b$ и $x_1 * x_2$\n\n"
          "> **Проверь себя.** $$\n> \\frac{1}{2}\n> $$\n>\n> **Ответ.** $c<d$\n\n"
          "> **Почему так?** $e_1 * e_2$")
    out = render(md)
    assert "$a&lt;b$ и $x_1 * x_2$" in out
    assert "$c&lt;d$" in out and "$e_1 * e_2$" in out and "\\frac{1}{2}" in out
    assert "<em>" not in out
    det = out[out.index("<details>"):]
    assert "$c&lt;d$" in det


def test_figure_only_with_title():
    out = render('![alt text](/api/v1/media/x.webp "Подпись <b>")')
    assert out == ('<figure><img alt="alt text" src="/api/v1/media/x.webp">'
                   '<figcaption>Подпись &lt;b&gt;</figcaption>\n</figure>')
    assert render("![схема](/api/v1/media/x.webp)") == '<p><img alt="схема" src="/api/v1/media/x.webp"></p>'
    assert render('text ![a](/api/v1/media/x.webp "t")').startswith("<p>text <img")  # not alone: unchanged
    assert "<figure" not in render('![a](/api/v1/media/x.webp "   ")')


def test_href_and_src_rules_inside_new_containers():
    md = ("> **Главное.** [ok](https://a.example) [bad](javascript:alert(1)) [rel](/x) [proto](//evil.example)\n\n"
          "---\n\n"
          '![a](https://evil.example/x.png "cap") ![b](data:image/png;base64,AA== "c")\n\n'
          '![c](/api/v1/media/../../etc "d")\n\n'
          "> **Почему так?** <a href='vbscript:x' onclick='y'>v</a> <img src='/api/v1/media/a.webp' onerror='x'>")
    out = render(md)
    assert '<a href="https://a.example" rel="noopener noreferrer" target="_blank">ok</a>' in out
    assert '<a rel="noopener noreferrer">bad</a>' in out and '<a href="/x" rel="noopener noreferrer">rel</a>' in out
    assert '<a rel="noopener noreferrer">proto</a>' in out
    assert '<figure><img alt="c"><figcaption>d</figcaption>' in out
    for src in re.findall(r'src="([^"]*)"', out):
        assert src.startswith("/api/v1/media/") and ".." not in src, src
    assert "javascript:" not in out and "vbscript:" not in out and "onclick" not in out and "onerror" not in out
    assert "data:" not in out


def test_merged_blockquotes_split_and_worked_keeps_trap():
    out = render("> **Главное.** a\n\n> **Ловушка.** b\n\n> **Разбор.** c\n>\n> **Ловушка.** d")
    assert out.count('<aside class="callout') == 3
    worked = out[out.index('<div class="worked">'):]
    assert '<aside class="callout callout--trap" role="note">' in worked


def test_check_without_answer_and_answer_hidden_only_from_answer():
    out = render("> **Проверь себя.** q")
    assert "callout--check" in out and "<details" not in out
    out = render("> **Проверь себя.**\n>\n> q\n>\n> **Ответ.** a")
    assert out.index("<p>q</p>") < out.index("<details>") < out.index("<strong>Ответ.</strong>")


def test_existing_blockquote_and_plain_bold_unchanged():
    assert render("> quote line") == "<blockquote>\n<p>quote line</p>\n</blockquote>"
    assert render("**Главное.** not a quote") == "<p><strong>Главное.</strong> not a quote</p>"
