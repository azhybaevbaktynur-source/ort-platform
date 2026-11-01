"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { startAssessmentAttempt } from "@/lib/lms/assessments";
import { LOBBY_REASONS, previewAttemptId, type AssessmentLobbyOut } from "@/lib/lms/assessmentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { Button, DescriptionList, Input, Select, type DescriptionItem } from "@/components/ui";
import { startAttemptWithCode } from "@/lib/lms/accommodations"; // Phase 7a S5
import { fmtDuration } from "@/components/lms/home/format";
import { AssessmentError } from "./AssessmentError";
import { LockedState, isModuleLocked } from "@/components/lms/pages/ApiError"; // Phase 8a fix1
import { fmtDateTime } from "./format";

const KNOWN_REASONS = new Set<string>(LOBBY_REASONS);

/** Student lobby: rules, sections and times, language choice, attempts left, Start / Resume (player route is built by F2). */
export function LobbyView({ lobby }: { lobby: AssessmentLobbyOut }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const player = (id: string) => `/${lang}/courses/${course.id}/attempts/${id}`;
  const initial: Lang = lobby.languages.includes(lang) ? lang : lobby.languages[0];
  const [language, setLanguage] = useState<Lang>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [accessCode, setAccessCode] = useState(""); // Phase 7a S5

  const title = pickLocalized(lobby.title, lang, course.default_language) || t("assessments.untitled");
  const description = pickLocalized(lobby.description, lang, course.default_language);
  const unlimited = lobby.allowed_attempts === -1;
  const left = unlimited ? null : Math.max(0, lobby.allowed_attempts - lobby.attempts_used);
  const resume = lobby.in_progress_attempt_id;
  // S7b, L1: say what happens on Start (the first timer runs at once).
  const firstSection = lobby.sections[0];
  const startHint = lobby.navigation === "section_forward_only" && firstSection?.time_limit_s
    ? t("assessments.lobby.startHintSection", { n: firstSection.pos })
    : lobby.time_limit_s || firstSection?.time_limit_s ? t("assessments.lobby.startHint") : "";

  // S11a, F3: after the last attempt the "My attempts" panel above already says "No attempts left".
  const exhausted = !lobby.can_start && lobby.reason === "attempts_exhausted";
  const info: DescriptionItem[] = [
    { key: "time", term: t("assessments.lobby.timeLimit"), description: lobby.time_limit_s ? fmtDuration(lobby.time_limit_s, t) : t("assessments.lobby.noLimit") },
    { key: "attempts", term: t("assessments.lobby.attemptsLeft"), description: left === null ? t("assessments.settings.unlimited") : t("assessments.lobby.attemptsUsed", { used: lobby.attempts_used, total: lobby.allowed_attempts }) },
  ];
  if (lobby.available_from) info.push({ key: "from", term: t("assessments.settings.availableFrom"), description: fmtDateTime(lobby.available_from) });
  if (lobby.available_until) info.push({ key: "until", term: t("assessments.settings.availableUntil"), description: fmtDateTime(lobby.available_until) });

  // --- Phase 7a S5: access code (PHASE_7A_DESIGN 3.8): asked only when the exam has one; resumes never ask ---
  const needsCode = !!lobby.requires_access_code && !resume;
  const codeError = error && ["access_code_required", "access_code_invalid"].includes((error as { code?: string }).code ?? "")
    ? t(`accommodations.accessCode.errors.${(error as { code: string }).code}`) : undefined;
  // --- Phase 7a S5 end ---

  const start = async () => {
    if (needsCode && !accessCode.trim()) { setError({ code: "access_code_required" }); return; } // Phase 7a S5
    setBusy(true);
    setError(null);
    try {
      const out = needsCode // Phase 7a S5
        ? await startAttemptWithCode(course.id, lobby.id, language, accessCode)
        : await startAssessmentAttempt(course.id, lobby.id, language);
      const id = previewAttemptId(out);
      if (id) router.push(player(id));
      else setError({ code: "unknown" });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h2 className="text-xl font-bold text-slate-900">{title}</h2>
        {description && <p className="mt-1 whitespace-pre-line text-sm text-slate-600">{description}</p>}
      </div>
      {/* S9: empty date rows are not shown; the total time reads in hours and minutes. */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <DescriptionList twoColumns items={info} />
      </div>
      <p className="rounded-xl bg-slate-50 px-3.5 py-2 text-sm text-slate-700">
        {lobby.navigation === "section_forward_only" ? t("assessments.lobby.forwardOnly") : t("assessments.lobby.freeNav")}
      </p>
      {/* Phase 7c UX: one untitled, unkeyed section (the quiz editor's hidden default section) has nothing to list. */}
      {!(lobby.sections.length === 1 && !pickLocalized(lobby.sections[0].title, lang, course.default_language) && !lobby.sections[0].key) && (
      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">{t("assessments.lobby.sections")}</h3>
        <ol className="space-y-1 text-sm">
          {lobby.sections.map((s) => {
            const name = pickLocalized(s.title, lang, course.default_language) || (s.key ? (t(`sections.${s.key}`) !== `sections.${s.key}` ? t(`sections.${s.key}`) : s.key) : t("assessments.section.n", { n: s.pos }));
            return (
              <li key={s.pos} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-3 py-0.5">
                <span className="text-slate-800">{s.pos}. {name}</span>
                <span className="whitespace-nowrap text-right text-slate-600">
                  {t("assessments.section.itemCount", { n: s.item_count })}
                  {s.time_limit_s ? ` · ${t("assessments.student.minutes", { n: Math.round(s.time_limit_s / 60) })}` : ""}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
      )}
      {!resume && lobby.languages.length > 1 && (
        <Select id="lobby-lang" label={t("assessments.lobby.language")} value={language}
          onChange={(e) => setLanguage(e.target.value as Lang)}
          options={lobby.languages.map((l) => ({ value: l, label: t(`courses.languages.${l}`) }))} />
      )}
      {!codeError && (isModuleLocked(error)
        ? <LockedState error={error} courseId={course.id} compact />
        : <AssessmentError error={error} />)}
      {resume ? (
        <div className="sticky bottom-3 z-10 rounded-2xl border border-slate-200 bg-white p-3 shadow-lg sm:static sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none">
          <Button className="w-full sm:w-auto" onClick={() => router.push(player(resume))}>{t("assessments.student.resume")}</Button>
        </div>
      ) : lobby.can_start ? (
        // Phones: the start row stays at the bottom of the screen with its hint (L1).
        <div className="sticky bottom-3 z-10 space-y-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-lg sm:static sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none">
          {/* --- Phase 7a S5/S6: access code field, only when the exam has a code (S6: above Start, so the code is
              entered first; exams without a code, ORT included, render exactly as before) --- */}
          {needsCode && (
            <Input id="lobby-code" label={t("accommodations.accessCode.lobbyLabel")} hint={t("accommodations.accessCode.lobbyHint")}
              autoComplete="off" spellCheck={false} maxLength={64} value={accessCode} error={codeError}
              onChange={(e) => { setAccessCode(e.target.value); if (codeError) setError(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") void start(); }} containerClassName="sm:max-w-sm" />
          )}
          <Button className="w-full sm:w-auto" loading={busy} onClick={() => void start()}>{t("assessments.lobby.start")}</Button>
          {startHint && <p className="text-sm text-slate-600">{startHint}</p>}
        </div>
      ) : exhausted ? null : (
        <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm text-amber-900">
          {lobby.reason && KNOWN_REASONS.has(lobby.reason) ? t(`assessments.lobby.reasons.${lobby.reason}`) : t("assessments.lobby.cannotStart")}
        </p>
      )}
    </div>
  );
}
