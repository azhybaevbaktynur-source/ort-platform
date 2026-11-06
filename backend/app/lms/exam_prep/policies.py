"""Route policies of the exam-prep routes (docs/ROADMAP_EXAM_PREP.md S2): the caller's own data in a course they
study in."""
_C = "/api/v1/courses/{course_id}/exam-prep"

EXAM_PREP_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _C): "course:attempt.read_own",
    ("GET", f"{_C}/library"): "course:attempt.read_own",
    ("PUT", f"{_C}/goal"): "course:attempt.read_own",
    ("DELETE", f"{_C}/goal"): "course:attempt.read_own",
}
