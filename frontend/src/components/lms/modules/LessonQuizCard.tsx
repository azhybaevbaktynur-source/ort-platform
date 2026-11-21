"use client";

// Lesson course requests C3 (R2): a quiz placed in the lesson (`link.placement = "lesson"`) is a card inside the lesson
// page, never the lobby: title, «N вопросов», the best result, ✓ when done, and one button that starts the attempt the
// way the lobby does (`POST …/assessments/{a}/attempts`) and opens the player with `?return=<this lesson>`, so the
// result leads back into Уроки. What the lobby alone can do (an access code, attempts used up, a closed or locked quiz)
// is said here with the lobby as the way on. The server decides every start.
import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CheckCircle2, ListChecks } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getAssessment, startAssessmentAttempt } from "@/lib/lms/assessments";
import { listMyAttempts } from "@/lib/lms/attempts";
import { LOBBY_REASONS, isStaffAssessment, previewAttemptId, type AssessmentLobbyOut } from "@/lib/lms/assessmentTypes";
import type { ItemStudentOut } from "@/lib/lms/modulesTypes";
import type { MyAttemptOut } from "@/lib/lms/attemptTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import { LockedState, isModuleLocked } from "@/components/lms/pages/ApiError";
import { withReturn } from "@/components/lms/player/returnPath";
import { Button, LoadingState, cn, focusRing } from "@/components/ui";
import { isDone } from "./lessons";

const KNOWN_REASONS = new Set<string>(LOBBY_REASONS);

/** The best result in whole percent over the student's own attempts with a visible result (null: none). */
export function bestPercent(attempts: MyAttemptOut[]): number | null {
  let best: number | null = null;
  for (const a of attempts) {
    const r = a.result;
    if (!r) continue;
    const possible = Number(r.points_possible);
    const raw = Number(r.raw_score);
    if (!Number.isFinite(possible) || possible <= 0 || !Number.isFinite(raw)) continue;
    const pct = Math.round((raw / possible) * 100);
    if (best === null || pct > best) best = pct;
  }
  return best;
}

export function LessonQuizCard({ item, lessonUrl, primary, readOnly, onOpen }: {
  item: ItemStudentOut;
  /** This lesson page: the player's and the result's `return`. */
  lessonUrl: string;
  /** The page's primary action (until the lesson is done). */
  primary: boolean;
  readOnly: boolean;
  /** The view fact, once the card's quiz is known. */
  onOpen: () => void;
}) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const assessmentId = item.link?.assessment_id ?? null;
  const base = `/${lang}/courses/${course.id}`;
  const lobbyHref = assessmentId ? `${base}/assessments/${assessmentId}` : null;
  const [lobby, setLobby] = useState<AssessmentLobbyOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [attemptsBest, setAttemptsBest] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const opened = useRef(onOpen);
  opened.current = onOpen;

  useEffect(() => {
    if (!assessmentId) return;
    let live = true;
    setLobby(null); setLoadError(null);
    getAssessment(course.id, assessmentId)
      .then((a) => {
        if (!live) return;
        if (isStaffAssessment(a)) { setLoadError({ code: "unknown" }); return; }
        setLobby(a);
        opened.current();
      })
      .catch((e) => { if (live) setLoadError(e); });
    return () => { live = false; };
  }, [course.id, assessmentId]);

  // the best result: the requirement's, else the student's own attempts (only when there are any)
  const reqBest = item.requirement?.best_score_percent ?? null;
  const used = lobby?.attempts_used ?? 0;
  useEffect(() => {
    if (!assessmentId || reqBest !== null || used === 0) return;
    let live = true;
    listMyAttempts(course.id, assessmentId)
      .then((rows) => { if (live) setAttemptsBest(bestPercent(rows)); })
      .catch(() => undefined); // the card works without it
    return () => { live = false; };
  }, [course.id, assessmentId, reqBest, used]);

  const lobbyLink = lobbyHref && (
    <Link href={lobbyHref} className={cn("inline-flex min-h-11 items-center gap-1 rounded-control text-sm font-medium text-brand-700 hover:underline", focusRing)}>
      {t("modules.lesson.quiz.toLobby")}<ArrowRight aria-hidden="true" className="h-4 w-4 shrink-0" />
    </Link>
  );

  if (!assessmentId) return null;
  if (loadError && !lobby) {
    return (
      <div className="space-y-2 rounded-card border border-slate-200 bg-white p-5">
        {isModuleLocked(loadError) ? <LockedState error={loadError} courseId={course.id} compact /> : <AssessmentError error={loadError} />}
        {lobbyLink}
      </div>
    );
  }
  if (!lobby) return <LoadingState rows={2} />;

  const title = pickLocalized(lobby.title, lang, course.default_language) || pickLocalized(item.title, lang, course.default_language) || t("assessments.untitled");
  const questions = lobby.sections.reduce((a, s) => a + (s.item_count || 0), 0);
  const best = reqBest ?? attemptsBest;
  const done = isDone(item);
  const resume = lobby.in_progress_attempt_id;
  const language = lobby.languages.includes(lang) ? lang : lobby.languages[0];
  const player = (id: string) => withReturn(`${base}/attempts/${id}`, lessonUrl);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await startAssessmentAttempt(course.id, lobby.id, language);
      const id = previewAttemptId(out);
      if (id) router.push(player(id));
      else setError({ code: "unknown" });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  let action: React.ReactNode;
  if (readOnly) {
    action = lobbyLink;
  } else if (resume) {
    action = (
      <Button size="lg" variant={primary ? "primary" : "secondary"} className="w-full sm:w-auto" onClick={() => router.push(player(resume))}>
        {t("modules.lesson.quiz.resume")}
      </Button>
    );
  } else if (lobby.can_start && lobby.requires_access_code) {
    // the code is entered in the lobby (it is asked before the start there)
    action = (
      <div className="space-y-1">
        <p className="text-sm leading-6 text-slate-700">{t("modules.lesson.quiz.accessCode")}</p>
        {lobbyLink}
      </div>
    );
  } else if (lobby.can_start) {
    action = (
      <Button size="lg" variant={primary ? "primary" : "secondary"} className="w-full sm:w-auto" loading={busy} onClick={() => void start()}>
        {used > 0 ? t("modules.lesson.quiz.again") : t("modules.lesson.quiz.start")}
      </Button>
    );
  } else {
    action = (
      <div className="space-y-1">
        <p role="status" className="rounded-control border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
          {lobby.reason && KNOWN_REASONS.has(lobby.reason) ? t(`assessments.lobby.reasons.${lobby.reason}`) : t("assessments.lobby.cannotStart")}
        </p>
        {lobbyLink}
      </div>
    );
  }

  return (
    <section aria-labelledby={`quiz-${item.id}`} className="space-y-4 rounded-card border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-brand-50 text-brand-700">
          <ListChecks className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          {/* the lesson's h1 already names the quiz: the card heading says what it is, the title stays for screen readers */}
          <h2 id={`quiz-${item.id}`} className="text-lg font-semibold leading-7 text-slate-900">
            {t("modules.lesson.quiz.eyebrow")}<span className="sr-only">: {title}</span>
          </h2>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm leading-5 text-slate-600">
            {questions > 0 && <span className="tabular-nums">{t("modules.lesson.quiz.questions", { count: questions })}</span>}
            {best !== null && <span className="tabular-nums">{t("modules.lesson.quiz.best", { percent: best })}</span>}
            {done && (
              <span className="inline-flex items-center gap-1 font-medium text-success-800">
                <CheckCircle2 aria-hidden="true" className="h-4 w-4" />{t("modules.lesson.quiz.done")}
              </span>
            )}
          </p>
        </div>
      </div>
      {error ? (isModuleLocked(error) ? <LockedState error={error} courseId={course.id} compact /> : <AssessmentError error={error} />) : null}
      {error ? lobbyLink : null}
      {action}
    </section>
  );
}
