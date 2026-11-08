"""Import warm-up (PERFORMANCE_AUDIT 5.3, slice S2). Service functions import some modules inside the function (to
break import cycles); the first request after a spin-up would pay those imports. `warm_up()` imports them once in the
lifespan instead. Imports only: no database, no network, no state."""
from __future__ import annotations

import importlib

# The read paths of the shell, the student pages and the attempt engine (function-level imports found with
# `grep -rn "^\s\+from app\." app`). Adding a module here is always safe; a missing one only costs the first request.
WARM_MODULES: tuple[str, ...] = (
    "app.lms.access.plans",
    "app.lms.access.settings",
    "app.lms.access.service",
    "app.lms.modules.service",
    "app.lms.modules.gate",
    "app.lms.modules.evaluator",
    "app.lms.modules.ids",
    "app.lms.modules.video",
    "app.lms.exam_prep.layout",
    "app.lms.courses.cover",
    "app.lms.courses.scopes",
    "app.lms.courses.lesson_courses",
    "app.lms.course_files.models",
    "app.lms.pages.models",
    "app.lms.announcements.service",
    "app.lms.enrollment_forms.models",
    "app.lms.teachers.models",
    "app.lms.guardian.service",
    "app.lms.privacy.gate",
    "app.lms.privacy.service",
    "app.lms.mfa.gate",
    "app.lms.student_view.allowlist",
    "app.lms.organizations.tree",
    "app.lms.core.ratelimit",
    "app.lms.attempts.engine",
    "app.lms.attempts.autosave",
    "app.lms.attempts.timing",
    "app.lms.attempts.results",
    "app.lms.attempts.grading",
    "app.lms.assessments.cache",
    "app.lms.grading.gradebook",
    "app.lms.home.service",
    "app.lms.home.bootstrap",
)


def warm_up() -> list[str]:
    """Imports every module of `WARM_MODULES`; returns their names. An import error propagates (the lifespan logs it)."""
    for name in WARM_MODULES:
        importlib.import_module(name)
    return list(WARM_MODULES)
