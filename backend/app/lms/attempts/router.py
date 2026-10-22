"""Student attempt routes (design section 5): start, state, content, autosave, section close, submit, result, review."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.authz import A, AuthzContext, get_authz
from app.db.session import get_db
from app.lms.attempts import autosave, engine, results, serializers as ser, sweep
from app.lms.attempts.schemas import (
    AnswersIn, AttemptStateOut, MyAttemptOut, SaveOut, StartIn, SubmitIn, SubmitOut,
)
from app.lms.core import clock
from app.lms.core.deps import get_lms_user
from app.lms.core.errors import Conflict, Forbidden, RateLimited, error_body
from app.lms.courses.service import load_course, require_course
from app.models.user import User

router = APIRouter()


# ------------------------------------------------------------------ start / mine (course scoped)

@router.post("/courses/{course_id}/assessments/{assessment_id}/attempts", response_model=AttemptStateOut)
def start_attempt(course_id: uuid.UUID, assessment_id: uuid.UUID, response: Response, background: BackgroundTasks,
                  data: Optional[StartIn] = None, ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ASSESSMENT_TAKE, course)
    state, created = engine.start_attempt(ctx.db, ctx, course, assessment_id, data or StartIn(), now=clock.now())
    response.status_code = 201 if created else 200
    sweep.maybe_schedule_sweep(background)
    return state


@router.get("/courses/{course_id}/assessments/{assessment_id}/attempts/mine", response_model=list[MyAttemptOut])
def my_attempts(course_id: uuid.UUID, assessment_id: uuid.UUID, ctx: AuthzContext = Depends(get_authz)):
    course = load_course(ctx.db, course_id)
    require_course(ctx, A.ATTEMPT_READ_OWN, course)
    return engine.list_my_attempts(ctx.db, ctx, course, assessment_id, now=clock.now())


# ------------------------------------------------------------------ attempt scoped

@router.get("/attempts/{attempt_id}", response_model=AttemptStateOut)
def get_attempt(attempt_id: str, background: BackgroundTasks, user: User = Depends(get_lms_user),
                db: Session = Depends(get_db)):
    state = engine.get_state(db, user, attempt_id, now=clock.now())
    sweep.maybe_schedule_sweep(background)
    return state


def _etag_matches(header: Optional[str], etag: str) -> bool:
    if not header:
        return False
    return any(part.strip() in (etag, "W/" + etag, "*") for part in header.split(","))


@router.get("/attempts/{attempt_id}/content")
def get_content(attempt_id: str, request: Request, section: Optional[int] = None,
                user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    """Free navigation and previews: the whole-exam payload (`section` is ignored). Forward-only: one section's
    payload, `?section=<pos>` (default: the current section); only sections up to the current one (after lazy
    advance) are served, later ones are 409 `section_not_current` (review finding 7)."""
    attempt, env = engine.load_attempt_bundle(db, user, attempt_id)
    if not engine.can_access(attempt, env):
        raise engine.attempt_not_found()
    plan = engine.plan_for(db, attempt)
    pos: Optional[int] = None
    if engine.sectioned_content(attempt, plan):
        engine.apply_lazy(db, attempt, engine.load_sections(db, attempt.id), plan, now=clock.now(), env=env)
        current = int(attempt.current_section_pos or 1)
        pos = current if section is None else section
        if pos < 1 or pos > current:
            raise Conflict("Section is not available yet", code="section_not_current")
    etag = f'"{engine.content_etag(attempt, plan, pos)}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=86400, immutable", "Vary": "Accept-Encoding"}
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    cache = engine.cache_api()
    if pos is None:
        payload = cache.get_student_payload(db, attempt.assessment_version_id, attempt.language)
    else:
        payload = cache.get_student_payload(db, attempt.assessment_version_id, attempt.language, pos)
    raw = _first(payload, "raw", "raw_bytes")
    gz = _first(payload, "gzipped", "gzip_bytes")
    if gz is not None and "gzip" in request.headers.get("accept-encoding", "").lower():
        headers["Content-Encoding"] = "gzip"
        return Response(content=gz, media_type="application/json", headers=headers)
    return Response(content=raw, media_type="application/json", headers=headers)


def _first(obj, *names):
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


@router.put("/attempts/{attempt_id}/answers", response_model=SaveOut)
def put_answers(attempt_id: str, data: AnswersIn, background: BackgroundTasks,
                content_length: Optional[int] = Header(None), user: User = Depends(get_lms_user),
                db: Session = Depends(get_db)):
    autosave.check_request_size(content_length)
    try:
        autosave.check_bucket(user.id)
    except RateLimited as exc:
        retry = (exc.details or {}).get("retry_after_seconds", 1)
        return JSONResponse(status_code=429, content=error_body(exc), headers={"Retry-After": str(retry)})
    out = autosave.save_answers(db, user, attempt_id, data.answers, now=clock.now())
    sweep.maybe_schedule_sweep(background)
    return out


@router.post("/attempts/{attempt_id}/sections/{pos}/close", response_model=AttemptStateOut)
def close_section(attempt_id: str, pos: int, background: BackgroundTasks, user: User = Depends(get_lms_user),
                  db: Session = Depends(get_db)):
    state = engine.close_section(db, user, attempt_id, pos, now=clock.now())
    sweep.maybe_schedule_sweep(background)
    return state


@router.post("/attempts/{attempt_id}/submit", response_model=SubmitOut)
def submit_attempt(attempt_id: str, background: BackgroundTasks, data: Optional[SubmitIn] = None,
                   user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    out = engine.submit(db, user, attempt_id, data or SubmitIn(), now=clock.now())
    sweep.maybe_schedule_sweep(background)
    return out


def _open_for_results(db: Session, user: User, attempt_id: str):
    """Own attempt with lazy expiry applied; results are only served when the policy allows it."""
    now = clock.now()
    attempt, env = engine.load_attempt_bundle(db, user, attempt_id)
    plan = engine.plan_for(db, attempt)
    engine.apply_lazy(db, attempt, engine.load_sections(db, attempt.id), plan, now=now, env=env)
    if not engine.can_access(attempt, env):
        raise engine.attempt_not_found()
    if not engine.results_available(env.assessment, attempt, now, staff=bool(attempt.is_preview)):
        raise Forbidden("Results are not available", code="results_not_available")
    return attempt, env, plan


@router.get("/attempts/{attempt_id}/result", response_model=ser.AttemptResultOut)
def get_result(attempt_id: str, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    attempt, _env, plan = _open_for_results(db, user, attempt_id)
    return results.result_out(attempt, plan)


@router.get("/attempts/{attempt_id}/review", response_model=ser.ReviewOut)
def get_review(attempt_id: str, user: User = Depends(get_lms_user), db: Session = Depends(get_db)):
    attempt, env, plan = _open_for_results(db, user, attempt_id)
    items = results.load_items(db, attempt.id)
    with_keys = results.keys_allowed(env.assessment) or bool(attempt.is_preview)
    return results.review_out(attempt, items, plan, None, with_keys=with_keys)
