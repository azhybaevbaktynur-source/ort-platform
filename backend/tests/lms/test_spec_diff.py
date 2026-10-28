"""Phase 8b S2: `diff.spec_diff` (pure, PHASE_8B_DESIGN 5.2, P8B-8) and `GET /exam-templates/{id}/diff` (6.1):
scalars, defaults, the lock scope as a set, sections matched by key then by ordinal among unkeyed ones,
parameters by key, deterministic order, and the route's authorization (readers compare versions; `to=draft` is a
404 for anyone who does not manage the template)."""
from __future__ import annotations

import uuid

from app.lms.exam_templates import diff, ids
from app.lms.exam_templates.schemas import SpecChange, SpecDiffOut
from app.lms.grading.seeds import ORT_MAIN_V1_ID
from tests.lms.exam_template_support import general_spec, ort_like_spec, ort_subject_spec
from tests.lms.s3_support import api, clean_rate_limits, db  # noqa: F401
from tests.lms.test_exam_templates_api import T, create_t, err, publish_t, published_template, tworld


def paths(changes: list[SpecChange]) -> list[tuple[str, str]]:
    return [(c.path, c.kind) for c in changes]


def test_identical_specs_have_no_changes():
    assert diff.spec_diff(general_spec(), general_spec()) == []
    # key order and omitted defaults do not matter: normalization first
    a = general_spec()
    b = {k: a[k] for k in reversed(list(a))}
    b.pop("parameters")
    b.pop("lock_scope")
    assert diff.spec_diff(a, b) == []
    assert diff.count_changes(ort_like_spec(), ort_like_spec()) == 0


def test_scalars_defaults_scoring_and_lock_scope():
    before = general_spec()
    after = general_spec(navigation="section_forward_only", result_view="ort", passage_display="numbered",
                         defaults={**before["defaults"], "allowed_attempts": -1, "shuffle_choices": False},
                         scoring={"grading_scheme_version_id": str(ORT_MAIN_V1_ID)},
                         lock_scope=["sections", "scheme"])
    ch = diff.spec_diff(before, after)
    assert paths(ch) == [("navigation", "changed"), ("passage_display", "changed"), ("result_view", "changed"),
                         ("defaults.allowed_attempts", "changed"), ("defaults.shuffle_choices", "changed"),
                         ("scoring.grading_scheme_version_id", "changed"), ("lock_scope", "changed")]
    by = {c.path: c for c in ch}
    assert (by["navigation"].before, by["navigation"].after) == ("free", "section_forward_only")
    assert (by["defaults.allowed_attempts"].before, by["defaults.allowed_attempts"].after) == (2, -1)
    assert by["scoring.grading_scheme_version_id"].before is None
    assert by["scoring.grading_scheme_version_id"].after == str(ORT_MAIN_V1_ID)
    assert (by["lock_scope"].before, by["lock_scope"].after) == ([], ["scheme", "sections"])
    # a lock scope in another order is the same set
    assert diff.spec_diff(general_spec(lock_scope=["scheme", "sections"]),
                          general_spec(lock_scope=["sections", "scheme"])) == []
    s = diff.summary(ch)
    assert (s.sections_added, s.sections_removed, s.sections_changed, s.fields_changed) == (0, 0, 0, 7)


def test_sections_matched_by_key_then_added_removed():
    before = general_spec(sections=[
        {"key": "a", "title": {"en": "A"}, "allowed_types": ["single_choice"], "allow_passages": False},
        {"key": "b", "title": {"en": "B"}, "allowed_types": ["essay"], "allow_passages": True, "min_items": 2},
    ])
    after = general_spec(sections=[
        {"key": "c", "title": {"en": "C"}, "allowed_types": ["essay"], "allow_passages": False},
        {"key": "a", "title": {"en": "A!"}, "time_limit_s": 600, "allowed_types": ["single_choice", "true_false"],
         "allow_passages": False},
    ])
    ch = diff.spec_diff(before, after)
    assert paths(ch) == [("sections[c]", "added"), ("sections[a].title", "changed"),
                         ("sections[a].time_limit_s", "changed"), ("sections[a].allowed_types", "changed"),
                         ("sections[b]", "removed")]
    added, removed = ch[0], ch[-1]
    assert added.before is None and added.after["key"] == "c" and added.section.position == 0   # 0-based index
    assert removed.after is None and removed.before["key"] == "b" and removed.section.position == 1
    assert removed.before["min_items"] == 2
    a_title = ch[1]
    assert a_title.section.key == "a" and a_title.section.position == 1 and a_title.section.title == {"en": "A!"}
    assert (a_title.before, a_title.after) == ({"en": "A"}, {"en": "A!"})
    s = diff.summary(ch)
    assert (s.sections_added, s.sections_removed, s.sections_changed, s.fields_changed) == (1, 1, 1, 3)


def test_unkeyed_sections_match_by_ordinal_and_mix_with_keyed_ones():
    before = general_spec(sections=[
        {"allowed_types": ["single_choice"], "allow_passages": False},
        {"key": "k", "allowed_types": ["single_choice"], "allow_passages": False},
        {"allowed_types": ["essay"], "allow_passages": False},
    ])
    after = general_spec(sections=[
        {"key": "k", "allowed_types": ["single_choice"], "allow_passages": True},
        {"allowed_types": ["single_choice"], "allow_passages": False, "time_limit_s": 300},
        {"allowed_types": ["essay"], "allow_passages": True},
        {"allowed_types": ["true_false"], "allow_passages": False},
    ])
    ch = diff.spec_diff(before, after)
    # after order (0-based): k (0), first unkeyed (1) ~ before 0, second unkeyed (2) ~ before 2, added (3)
    assert paths(ch) == [("sections[k].allow_passages", "changed"), ("sections[1].time_limit_s", "changed"),
                         ("sections[2].allow_passages", "changed"), ("sections[3]", "added")]
    assert ch[1].section.position == 1 and ch[1].section.key is None
    assert ch[3].after["allowed_types"] == ["true_false"]
    # a keyed section whose key disappears is removed, not renamed
    ch = diff.spec_diff(general_spec(sections=[{"key": "x", "allowed_types": ["essay"], "allow_passages": False}]),
                        general_spec(sections=[{"key": "y", "allowed_types": ["essay"], "allow_passages": False}]))
    assert paths(ch) == [("sections[y]", "added"), ("sections[x]", "removed")]


def test_parameters_matched_by_key():
    before = ort_subject_spec()
    after = ort_subject_spec()
    after["parameters"][0]["options"] = list(reversed(before["parameters"][0]["options"]))
    after["parameters"].append({"key": "extra", "kind": "choice", "options": ["o1"], "binds": "sections[0].key"})
    ch = diff.spec_diff(before, after)
    assert paths(ch) == [("parameters[subject].options", "changed"), ("parameters[extra]", "added")]
    ch = diff.spec_diff(after, before)
    assert paths(ch) == [("parameters[subject].options", "changed"), ("parameters[extra]", "removed")]
    assert ch[1].before["key"] == "extra" and ch[1].after is None


def test_order_is_top_level_then_sections_then_parameters():
    before = ort_subject_spec()
    after = ort_subject_spec()
    after["navigation"] = "free"
    after["lock_scope"] = []
    after["sections"].append({"key": "tail", "allowed_types": ["essay"], "allow_passages": False})
    after["parameters"][0]["options"] = after["parameters"][0]["options"][:3]
    ch = diff.spec_diff(before, after)
    kinds = [p.split("[")[0].split(".")[0] for p, _ in paths(ch)]
    assert kinds == ["navigation", "lock_scope", "sections", "parameters"]
    # the result is a plain structure of the two specs: nothing else
    out = SpecDiffOut(from_=1, to="draft", changes=ch, summary=diff.summary(ch)).model_dump(by_alias=True)
    assert set(out) == {"from", "to", "changes", "summary"} and out["from"] == 1


# ------------------------------------------------------------------------------------------------ the route

V1 = general_spec(sections=[{"key": "a", "allowed_types": ["single_choice"], "allow_passages": False}])
V2 = general_spec(navigation="section_forward_only", sections=[
    {"key": "a", "time_limit_s": 600, "allowed_types": ["single_choice"], "allow_passages": False},
    {"key": "b", "allowed_types": ["essay"], "allow_passages": False}])
DRAFT = general_spec(sections=[{"key": "a", "allowed_types": ["essay"], "allow_passages": False}])


async def _two_versions(api, user, **kw):
    t = await published_template(api, user, spec=V1, **kw)
    cur = (await api.call(user, "GET", f"{T}/{t['id']}")).json()
    res = await api.call(user, "PATCH", f"{T}/{t['id']}", json={"draft_rev": cur["draft_rev"], "draft_spec": V2})
    assert res.status_code == 200, res.text
    assert (await publish_t(api, user, t["id"])).status_code == 200
    cur = (await api.call(user, "GET", f"{T}/{t['id']}")).json()
    res = await api.call(user, "PATCH", f"{T}/{t['id']}", json={"draft_rev": cur["draft_rev"], "draft_spec": DRAFT})
    assert res.status_code == 200, res.text
    return t["id"]


async def test_diff_route_versions_and_draft(db, api):
    w = tworld(db)
    tid = await _two_versions(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    res = await api.call(w.OA, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": 2})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["from"], body["to"]) == (1, 2)
    assert [(c["path"], c["kind"]) for c in body["changes"]] == [
        ("navigation", "changed"), ("sections[a].time_limit_s", "changed"), ("sections[b]", "added")]
    assert body["summary"] == {"sections_added": 1, "sections_removed": 0, "sections_changed": 1,
                               "fields_changed": 2}
    assert set(body) == {"from", "to", "changes", "summary"}
    # draft target for a manager; reverse direction works too
    res = await api.call(w.OA, "GET", f"{T}/{tid}/diff", params={"from": 2, "to": "draft"})
    assert res.status_code == 200, res.text
    assert res.json()["to"] == "draft"
    assert [(c["path"], c["kind"]) for c in res.json()["changes"]] == [
        ("navigation", "changed"), ("sections[a].time_limit_s", "changed"), ("sections[a].allowed_types", "changed"),
        ("sections[b]", "removed")]
    assert (await api.call(w.OA, "GET", f"{T}/{tid}/diff", params={"from": 2, "to": 1})).json()["summary"] == {
        "sections_added": 0, "sections_removed": 1, "sections_changed": 1, "fields_changed": 2}
    # the template payload counts the same draft diff
    me = (await api.call(w.OA, "GET", f"{T}/{tid}")).json()
    assert me["unpublished_changes"] == 4


async def test_diff_route_errors(db, api):
    w = tworld(db)
    tid = await _two_versions(api, w.PA)
    res = await api.call(w.PA, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": 9})
    assert res.status_code == 404 and err(res) == ids.E_VERSION_NOT_FOUND
    res = await api.call(w.PA, "GET", f"{T}/{tid}/diff", params={"from": 7, "to": 1})
    assert res.status_code == 404 and err(res) == ids.E_VERSION_NOT_FOUND
    res = await api.call(w.PA, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": "latest"})
    assert res.status_code == 422 and err(res) == ids.E_DIFF_TARGET_INVALID
    res = await api.call(w.PA, "GET", f"{T}/{tid}/diff", params={"from": 1})
    assert res.status_code == 422
    res = await api.call(w.PA, "GET", f"{T}/{tid}/diff", params={"from": 0, "to": 1})
    assert res.status_code == 422
    # draft target without a draft
    cur = (await api.call(w.PA, "GET", f"{T}/{tid}")).json()
    assert (await api.call(w.PA, "PATCH", f"{T}/{tid}", json={"draft_rev": cur["draft_rev"], "draft_spec": None})
            ).status_code == 200
    res = await api.call(w.PA, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": "draft"})
    assert res.status_code == 422 and err(res) == ids.E_DIFF_TARGET_INVALID
    assert (await api.call(w.PA, "GET", f"{T}/{uuid.uuid4()}/diff", params={"from": 1, "to": 2})).status_code == 404


async def test_diff_route_authorization(db, api):
    w = tworld(db)
    tid = await _two_versions(api, w.OA, owner_scope="organization", organization_id=w.org.id)
    # readers (teachers and course staff of the organization, 7b `can_read`) compare versions, never the draft
    for reader in (w.TA, w.TB, w.AS):
        res = await api.call(reader, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": 2})
        assert res.status_code == 200, (reader.id, res.text)
        res = await api.call(reader, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": "draft"})
        assert res.status_code == 404 and err(res) == ids.E_TEMPLATE_NOT_FOUND, (reader.id, res.text)
    # managers see the draft diff
    for manager in (w.OA, w.PA):
        res = await api.call(manager, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": "draft"})
        assert res.status_code == 200, (manager.id, res.text)
    # outsiders, students and another organization: 404 on everything
    for u in (w.S, w.X, w.TC):
        for to in (2, "draft"):
            res = await api.call(u, "GET", f"{T}/{tid}/diff", params={"from": 1, "to": to})
            assert res.status_code == 404, (u.id, to, res.text)
    # a teacher template: its owner and the org admin manage it, the other teacher of the org cannot read it
    res = await create_t(api, w.TA, owner_scope="teacher", organization_id=w.org.id, spec=V1)
    mine = res.json()["id"]
    assert (await publish_t(api, w.TA, mine)).status_code == 200
    res = await api.call(w.TA, "GET", f"{T}/{mine}/diff", params={"from": 1, "to": 1})
    assert res.status_code == 200 and res.json()["changes"] == []
    assert (await api.call(w.TB, "GET", f"{T}/{mine}/diff", params={"from": 1, "to": 1})).status_code == 404
    assert (await api.call(w.OA, "GET", f"{T}/{mine}/diff", params={"from": 1, "to": 1})).status_code == 200
