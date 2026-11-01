"""Student view (UX rework, UX_REWORK_DESIGN F): a real student session for a per-course test student.

The server treats the test student as an ordinary student with an active student enrollment; there is no role
switching in `core/authz.py`. Three things differ: `allowlist.py` limits it to the routes the student screens use,
`authz.can` lets it work in its own draft course, and staff queries exclude it (`enrollments.models.not_test_enrollment`
and `is_test_student` filters)."""
