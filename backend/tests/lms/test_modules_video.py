"""Student UI U7 (STUDENT_UI_DESIGN 4.4): `ItemStudentOut.video` for allowlisted YouTube / Vimeo `url` items.

The parser is strict (https, exact host, fixed path, validated id); lookalike hosts, user-info tricks, other schemes and
malformed ids stay plain links. Locked rows never carry `video` (like `link`), the teacher shape is unchanged."""
import pytest

from app.lms.modules.video import parse_video
from tests.lms.modules_support import C, add_prerequisite, make_item, make_module, make_page, structure_world
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401

YT = "dQw4w9WgXcQ"


@pytest.mark.parametrize("url,expected", [
    (f"https://www.youtube.com/watch?v={YT}", ("youtube", YT)),
    (f"https://youtube.com/watch?v={YT}&t=42s", ("youtube", YT)),
    (f"https://m.youtube.com/watch?feature=share&v={YT}", ("youtube", YT)),
    (f"https://WWW.YouTube.com/watch?v={YT}", ("youtube", YT)),
    (f"https://youtu.be/{YT}", ("youtube", YT)),
    (f"https://youtu.be/{YT}?si=abc", ("youtube", YT)),
    (f"https://www.youtube.com/embed/{YT}", ("youtube", YT)),
    (f"https://www.youtube.com/embed/{YT}/", ("youtube", YT)),
    (f"https://www.youtube-nocookie.com/embed/{YT}", ("youtube", YT)),
    (f"https://youtube-nocookie.com/embed/{YT}?rel=0", ("youtube", YT)),
    (f"https://www.youtube.com/shorts/{YT}", ("youtube", YT)),
    (f"https://youtu.be/{YT}#t=10", ("youtube", YT)),
    ("https://vimeo.com/76979871", ("vimeo", "76979871")),
    ("https://www.vimeo.com/76979871", ("vimeo", "76979871")),
    ("https://player.vimeo.com/video/76979871", ("vimeo", "76979871")),
    ("https://player.vimeo.com/video/76979871?h=abc", ("vimeo", "76979871")),
])
def test_allowlisted_urls(url, expected):
    v = parse_video(url)
    assert v is not None and (v["provider"], v["id"]) == expected


@pytest.mark.parametrize("url", [
    # scheme
    f"http://www.youtube.com/watch?v={YT}",
    f"javascript:alert(1)//https://youtu.be/{YT}",
    "javascript:alert(document.cookie)",
    f"data:text/html,https://youtu.be/{YT}",
    f"//youtu.be/{YT}",
    f"youtu.be/{YT}",
    f"ftp://youtu.be/{YT}",
    # lookalike and suffix hosts
    f"https://youtube.com.evil.com/watch?v={YT}",
    f"https://www.youtube.com.evil.com/embed/{YT}",
    f"https://evilyoutube.com/watch?v={YT}",
    f"https://evil.youtube.com/watch?v={YT}",
    f"https://youtu.be.evil.com/{YT}",
    f"https://notyoutu.be/{YT}",
    "https://vimeo.com.evil.com/76979871",
    "https://player.vimeo.com.evil.com/video/76979871",
    "https://evilvimeo.com/76979871",
    f"https://youtube.com./watch?v={YT}",
    f"https://youtube%2Ecom/watch?v={YT}",
    # user info, ports, backslashes, whitespace
    f"https://www.youtube.com@evil.com/watch?v={YT}",
    f"https://evil.com@www.youtube.com/watch?v={YT}",
    f"https://user:pass@youtu.be/{YT}",
    f"https://youtu.be:8443/{YT}",
    f"https://youtu.be:443/{YT}",
    f"https://evil.com\\@youtu.be/{YT}",
    f"https://youtu.be\\evil.com/{YT}",
    f"https://youtu.be/{YT} ",
    f" https://youtu.be/{YT}",
    f"https://youtu.be/{YT}\n",
    f"https://youtu.be/\t{YT}",
    # bad ids and paths
    "https://youtu.be/short",
    f"https://youtu.be/{YT}x",
    "https://youtu.be/dQw4w9WgXc!",
    "https://youtu.be/<script>abc",
    f"https://youtu.be/{YT}/extra",
    f"https://youtu.be//{YT}",
    "https://www.youtube.com/watch",
    "https://www.youtube.com/watch?v=",
    f"https://www.youtube.com/watch?v={YT}&v=aaaaaaaaaaa",
    f"https://www.youtube.com/watch/{YT}",
    f"https://www.youtube.com/embed/{YT}/extra",
    f"https://www.youtube.com/v/{YT}",
    f"https://www.youtube.com/playlist?list={YT}",
    f"https://www.youtube.com/?v={YT}",
    f"https://www.youtube-nocookie.com/watch?v={YT}",
    f"https://youtu.be/embed/{YT}",
    "https://vimeo.com/abc",
    "https://vimeo.com/123/abcdef",
    "https://vimeo.com/channels/staffpicks/76979871",
    "https://vimeo.com/1234567890123",
    "https://player.vimeo.com/76979871",
    "https://player.vimeo.com/video/76979871abc",
    "https://player.vimeo.com/video/-1",
    "https://example.org",
    "",
    None,
    "https://" + "y" * 3000,
])
def test_everything_else_stays_a_link(url):
    assert parse_video(url) is None


async def test_student_outline_carries_video_only_for_allowlisted_unlocked_url_items(db, api):
    w = structure_world(db)
    m1 = make_module(db, w.course, w.O, title={"en": "Lessons"})
    yt = make_item(db, m1, f"https://youtu.be/{YT}", title_override={"en": "Comparison"}, requirement=("mark_done",))
    vimeo = make_item(db, m1, "https://vimeo.com/76979871")
    plain = make_item(db, m1, "https://example.org/notes")
    evil = make_item(db, m1, f"https://youtube.com.evil.com/watch?v={YT}")
    page = make_item(db, m1, make_page(db, w.course, w.O, title="Notes"))
    gated = make_module(db, w.course, w.O, title={"en": "Later"})
    add_prerequisite(db, gated, m1)
    locked = make_item(db, gated, f"https://youtu.be/{YT}")

    r = await api.call(w.S, "GET", f"{C(w)}/modules")
    assert r.status_code == 200
    items = {it["id"]: it for m in r.json()["modules"] for it in m["items"]}
    assert items[str(yt.id)]["video"] == {"provider": "youtube", "id": YT}
    assert items[str(vimeo.id)]["video"] == {"provider": "vimeo", "id": "76979871"}
    assert items[str(plain.id)]["video"] is None and items[str(plain.id)]["link"]["url"] == "https://example.org/notes"
    assert items[str(evil.id)]["video"] is None
    assert items[str(page.id)]["video"] is None
    # a locked row carries neither the address nor the video id
    assert items[str(locked.id)]["locked"] is True
    assert items[str(locked.id)]["video"] is None and items[str(locked.id)]["link"] is None

    # staff: unchanged (the video is a URL item; no `video` field)
    staff = (await api.call(w.O, "GET", f"{C(w)}/modules")).json()
    for m in staff["modules"]:
        for it in m["items"]:
            assert "video" not in it

    # the facts route returns the same shape with the video
    r = await api.call(w.S, "POST", f"{C(w)}/modules/{m1.id}/items/{yt.id}/done", json={"done": True})
    assert r.status_code == 200
    row = next(it for it in r.json()["items"] if it["id"] == str(yt.id))
    assert row["video"] == {"provider": "youtube", "id": YT} and row["requirement"]["met"] is True
