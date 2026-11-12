"""Exam families and subjects of courses (docs/phases/STUDENT_IA_DESIGN.md 6.1; migration 0033).

`courses.exam_family` groups a course under an exam («ОРТ», «НЦТ»; null = «Другие курсы»), `courses.subject` names
the subject course of that exam (null = the family's main course). The columns carry no CHECK: the values live here and
`courses.service.update_course` validates against them (422 `exam_family_invalid` / `subject_invalid`). Adding a family
or a subject is one line here plus the label keys `exam.family.{key}` / `exam.subject.{key}` in en, ky and ru."""
from __future__ import annotations

FAMILIES: tuple[str, ...] = ("ort", "nct")
SUBJECTS: tuple[str, ...] = (
    "math", "physics", "chemistry", "biology", "history", "geography", "kyrgyz", "russian", "english", "literature",
)

E_FAMILY_INVALID = "exam_family_invalid"
E_SUBJECT_INVALID = "subject_invalid"
E_FAMILY_FORBIDDEN = "exam_family_forbidden"
