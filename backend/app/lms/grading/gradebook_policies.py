"""Route policies of the gradebook / student grade reads (slice G3, design 4 and 5)."""
_C = "/api/v1/courses/{course_id}"

GRADEBOOK_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/gradebook"): "course:attempt.read_all",
    ("GET", f"{_C}/submissions/{{submission_id}}"): "course:attempt.read_all",
    ("GET", f"{_C}/grades/mine"): "course:grades.read_own",
}
