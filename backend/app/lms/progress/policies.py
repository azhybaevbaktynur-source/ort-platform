"""Route policies of the progress routes (PHASE_10_DESIGN 4)."""
_C = "/api/v1/courses/{course_id}"

PROGRESS_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/my/progress"): "course:attempt.read_own",
    ("GET", f"{_C}/my/mistakes"): "course:attempt.read_own",
    ("PUT", f"{_C}/my/goal"): "course:attempt.read_own",
    ("DELETE", f"{_C}/my/goal"): "course:attempt.read_own",
}
