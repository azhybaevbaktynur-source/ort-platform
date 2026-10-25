"""Exact key sets of the student-facing serializers (design 7.5); no forbidden keys anywhere in a payload."""
from app.lms.courses.schemas import CourseCard, CourseStaffOut, CourseStudentOut, JoinOut
from app.lms.enrollments.schemas import MyEnrollmentOut, RosterEntryOut, StaffPublicOut
from tests.lms.s3_support import api, clean_rate_limits, db, enroll, make_course, make_user, teacher  # noqa: F401

FORBIDDEN = {"join_code", "enrollment_limit", "email", "user_id", "enrollment_mode", "visibility",
             "active_student_count", "owner", "is_owner", "unlisted_by_admin", "invite_token_hash"}


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def test_declared_key_sets():
    assert set(CourseCard.model_fields) == {"id", "title", "languages", "default_language", "status", "my_role",
                                            "owner_display_name", "starts_at", "ends_at", "deleted_at"}
    assert set(CourseStudentOut.model_fields) == {"id", "title", "description", "languages", "default_language",
                                                  "status", "starts_at", "ends_at", "owner_display_name",
                                                  "my_enrollment", "organization_id", "organization_name"}
    assert set(CourseStaffOut.model_fields) == set(CourseStudentOut.model_fields) | {
        "join_code", "enrollment_mode", "enrollment_limit", "visibility", "unlisted_by_admin",
        "active_student_count", "owner", "is_owner", "created_at", "updated_at", "published_at", "concluded_at"}
    assert set(StaffPublicOut.model_fields) == {"display_name", "role"}
    assert set(MyEnrollmentOut.model_fields) == {"id", "course_id", "role", "state", "activated_at"}
    assert set(JoinOut.model_fields) == {"course", "enrollment", "already_enrolled"}
    assert set(RosterEntryOut.model_fields) == {"enrollment_id", "user", "role", "state", "source", "activated_at",
                                                "removed_at", "is_owner"}


async def test_student_payloads_have_no_forbidden_keys(db, api):
    t, s = teacher(db, display_name=None), make_user(db)
    c = make_course(db, t, status="published", enrollment_limit=10)
    other = make_user(db)
    enroll(db, c, other)
    join = await api.call(s, "POST", "/courses/join", json={"code": c.join_code})
    assert join.status_code == 200
    payloads = {
        "join": join.json(),
        "list": (await api.call(s, "GET", "/courses")).json(),
        "get": (await api.call(s, "GET", f"/courses/{c.id}")).json(),
        "people": (await api.call(s, "GET", f"/courses/{c.id}/people")).json(),
        "trash": (await api.call(s, "GET", "/courses/trash")).json(),
    }
    for name, body in payloads.items():
        assert not (set(walk_keys(body)) & FORBIDDEN), (name, set(walk_keys(body)) & FORBIDDEN)
    assert set(payloads["get"]) == set(CourseStudentOut.model_fields)
    assert set(payloads["join"]) == set(JoinOut.model_fields)
    assert set(payloads["join"]["course"]) == set(CourseCard.model_fields)
    assert set(payloads["get"]["my_enrollment"]) == set(MyEnrollmentOut.model_fields)
    assert all(set(i) == set(CourseCard.model_fields) for i in payloads["list"]["items"])
    assert all(set(i) == {"display_name", "role"} for i in payloads["people"]["items"])
    # owner without a display name shows a dash to students, never the email local part
    assert payloads["get"]["owner_display_name"] == "—"
    assert t.email.split("@")[0] not in str(payloads)
    # staff view does expose the code
    assert (await api.call(t, "GET", f"/courses/{c.id}")).json()["join_code"] == c.join_code
