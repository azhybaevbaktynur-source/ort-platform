"use client";

import React, { useCallback, useEffect, useState } from "react";
import { ArrowRight, CircleAlert, Clock, GraduationCap, Info } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { getMe } from "@/lib/lms/courses";
import { listMyTeacherRequests, submitTeacherRequest } from "@/lib/lms/teacher";
import type { MeOut, MyTeacherRequestOut } from "@/lib/lms/types";
import { fmtApiDate, fmtApiDateTimeShort, parseApiDate } from "@/lib/format";
import { Button, Checkbox, DescriptionList, Input, LinkButton, LoadingState, Textarea, cn } from "@/components/ui";
import { PolicyAcceptField, useOwnPolicies } from "@/components/auth/SignUpFields";
import { getMyPrivacy, ownPolicyIds, type AgeBand } from "@/components/privacy/privacyApi";
import { LoadError, apiErrorText } from "@/components/lms/org/OrgUi";

// The API's rules (`TeacherRequestIn`), so a mistake is shown beside its field.
const TEXT_MAX = 200;
const MESSAGE_MAX = 2000;
const PHONE_MAX = 32;
const PHONE_MIN_DIGITS = 5;
function phoneLooksValid(phone: string): boolean {
  const v = phone.trim();
  return /^[0-9 +\-()]{5,32}$/.test(v) && v.replace(/[^0-9]/g, "").length >= PHONE_MIN_DIGITS;
}

interface Loaded {
  band: AgeBand | null;
  me: MeOut | null;
  requests: MyTeacherRequestOut[];
}

type T = (key: string, params?: Record<string, string | number>) => string;

function Panel({ icon, title, tone, children }: { icon: React.ReactNode; title: string; tone: "neutral" | "success" | "warning" | "danger"; children?: React.ReactNode }) {
  const color = { neutral: "bg-slate-100 text-slate-700", success: "bg-success-50 text-success-700", warning: "bg-warning-50 text-warning-800", danger: "bg-danger-50 text-danger-700" }[tone];
  return (
    <div role="status">
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl [&>svg]:h-5 [&>svg]:w-5", color)}>{icon}</span>
        <h2 className="min-w-0 break-words text-xl font-bold leading-7 text-slate-900">{title}</h2>
      </div>
      <div className="mt-3 space-y-3 text-base leading-7 text-slate-700">{children}</div>
    </div>
  );
}

function Notice({ tone, children }: { tone: "info" | "danger"; children: React.ReactNode }) {
  const Icon = tone === "info" ? Info : CircleAlert;
  return (
    <div className={cn("mb-4 flex items-start gap-2 rounded-xl border p-3 text-sm leading-5",
      tone === "info" ? "border-sky-200 bg-sky-50 text-sky-900" : "border-danger-200 bg-danger-50 text-danger-800")}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 break-words">{children}</div>
    </div>
  );
}

/** What the person sent, for the pending page. Old requests have only their message. */
function RequestDetails({ request }: { request: MyTeacherRequestOut }) {
  const { lang, t } = useTranslation();
  const items = [
    { key: "name", term: t("teacherApply.field.name"), description: request.applicant_name },
    { key: "school", term: t("teacherApply.field.school"), description: request.school },
    { key: "subject", term: t("teacherApply.field.subject"), description: request.subject },
    { key: "phone", term: t("teacherApply.field.phone"), description: request.phone },
    { key: "message", term: t("teacherApply.field.message"), description: request.message && <span className="whitespace-pre-wrap">{request.message}</span> },
    { key: "sent", term: t("teacherApply.pending.sent"), description: fmtApiDateTimeShort(request.created_at, lang) },
  ].filter((item) => item.description);
  return <DescriptionList layout="columns" items={items} className="rounded-xl border border-slate-200 p-3" />;
}

/** Step 3, and every other state of a signed-in person. The server decides; this page only says where they stand. */
export function ApplicationStep({ onSubmitted }: { onSubmitted: () => void }) {
  const { lang, t } = useTranslation();
  const { userProfile } = useAuth();
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<unknown>(null);
  const testStudent = !!userProfile?.is_test_student;

  const load = useCallback(async () => {
    setError(null);
    try {
      const privacy = await getMyPrivacy();
      // An under-14 account stops here: the consent gate would send every other call to the privacy page.
      if (privacy.age_band === "under_14") { setData({ band: privacy.age_band, me: null, requests: [] }); return; }
      const [me, requests] = await Promise.all([getMe(), listMyTeacherRequests()]);
      setData({ band: privacy.age_band, me, requests });
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { if (!testStudent) void load(); }, [load, testStudent]);

  const home = `/${lang}/courses`;
  if (testStudent) {
    return <Panel icon={<CircleAlert />} tone="neutral" title={t("teacherApply.refused.title")}><p>{t("lms.errors.test_student_forbidden")}</p></Panel>;
  }
  if (error) return <LoadError error={error} onRetry={() => void load()} />;
  if (!data) return <LoadingState label={t("lms.common.loading")} />;

  const { band, me, requests } = data;
  const latest = requests[0] ?? null;
  const status = me?.teacher_status ?? "none";

  if (status === "approved") {
    return (
      <Panel icon={<GraduationCap />} tone="success" title={t("teacherApply.approved.title")}>
        <p>{t("teacherApply.approved.body")}</p>
        <LinkButton href={`${home}?view=teaching`} size="lg" className="w-full sm:w-auto">{t("teacherApply.approved.link")}</LinkButton>
      </Panel>
    );
  }
  if (status === "pending" || latest?.status === "pending") {
    return (
      <Panel icon={<Clock />} tone="warning" title={t("teacherApply.pending.title")}>
        <p>{t("teacherApply.pending.body")}</p>
        {latest?.status === "pending" && <RequestDetails request={latest} />}
      </Panel>
    );
  }
  const reapplyAt = latest?.status === "rejected" ? latest.reapply_available_at : null;
  const waiting = status !== "revoked" && (parseApiDate(reapplyAt)?.getTime() ?? 0) > Date.now();
  if (waiting) {
    return (
      <Panel icon={<CircleAlert />} tone="danger" title={t("teacherApply.rejected.title")}>
        {latest?.reason && <p className="break-words"><strong>{t("teacherRequest.reason")}:</strong> {latest.reason}</p>}
        <p>{t("teacherApply.rejected.wait", { date: fmtApiDate(reapplyAt, lang) })}</p>
        <LinkButton href={home} variant="secondary" className="w-full sm:w-auto">{t("teacherOnly.back")}</LinkButton>
      </Panel>
    );
  }
  if (band === "under_14" || band === "14_17") {
    return (
      <Panel icon={<CircleAlert />} tone="neutral" title={t("teacherApply.minor.title")}>
        <p>{t("teacherApply.minor.body")}</p>
        <LinkButton href={home} variant="secondary" className="w-full sm:w-auto">{t("teacherOnly.back")}</LinkButton>
      </Panel>
    );
  }
  return (
    <ApplicationForm
      needsAge={band === null}
      initialName={me?.display_name ?? ""}
      revoked={status === "revoked"}
      canAlreadyCreate={!!me?.can_create_courses && status !== "revoked"}
      rejected={latest?.status === "rejected" ? latest : null}
      onSubmitted={() => { onSubmitted(); window.scrollTo({ top: 0 }); void load(); }}
      onStateChanged={() => void load()}
    />
  );
}

type FieldKey = "name" | "school" | "subject" | "phone" | "age" | "policies";
const FIRST_INVALID: FieldKey[] = ["name", "school", "subject", "phone", "age", "policies"];
const fieldId = (key: FieldKey) => `apply-${key}`;

function ApplicationForm({ needsAge, initialName, revoked, canAlreadyCreate, rejected, onSubmitted, onStateChanged }: {
  needsAge: boolean;
  initialName: string;
  revoked: boolean;
  canAlreadyCreate: boolean;
  rejected: MyTeacherRequestOut | null;
  onSubmitted: () => void;
  onStateChanged: () => void;
}) {
  const { lang, t } = useTranslation();
  const [name, setName] = useState(initialName);
  const [school, setSchool] = useState("");
  const [subject, setSubject] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [adult, setAdult] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const policyState = useOwnPolicies(needsAge);

  const validate = (): Partial<Record<FieldKey, string>> => {
    const found: Partial<Record<FieldKey, string>> = {};
    const required = t("teacherApply.error.required");
    if (!name.trim()) found.name = required;
    if (!school.trim()) found.school = required;
    if (!subject.trim()) found.subject = required;
    if (!phoneLooksValid(phone)) found.phone = t("teacherApply.error.phone");
    if (needsAge && !adult) found.age = t("teacherApply.error.age");
    if (needsAge && !accepted) found.policies = t("teacherApply.error.policies");
    return found;
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    const found = validate();
    setErrors(found);
    const first = FIRST_INVALID.find((key) => found[key]);
    if (first) {
      document.getElementById(fieldId(first))?.focus();
      return;
    }
    setBusy(true);
    try {
      await submitTeacherRequest({
        applicant_name: name.trim(), school: school.trim(), subject: subject.trim(), phone: phone.trim(),
        ...(message.trim() ? { message: message.trim() } : {}),
        ...(needsAge ? { age_confirmed: true, policy_version_ids: ownPolicyIds(policyState.policies ?? []) } : {}),
      });
      onSubmitted();
    } catch (err) {
      setServerError(errorText(t, err, lang));
      // The person's state moved on (a decision, another tab): the page shows where they stand now.
      const code = (err as { code?: string }).code;
      if (code === "request_pending" || code === "already_teacher" || code === "reapply_wait" || code === "teacher_age_required") onStateChanged();
      if (code === "age_confirmation_required") policyState.reload();
    } finally {
      setBusy(false);
    }
  };

  const fieldError = (key: FieldKey) => errors[key] ? <span role="alert">{errors[key]}</span> : undefined;
  const clear = (key: FieldKey) => setErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));
  return (
    <div>
      <h2 className="mb-1 text-xl font-bold leading-7 text-slate-900">{t("teacherApply.form.title")}</h2>
      <p className="mb-4 text-sm leading-5 text-slate-600">{t("teacherApply.form.intro")}</p>
      {revoked && <Notice tone="danger">{t("teacherApply.form.revoked")}</Notice>}
      {canAlreadyCreate && <Notice tone="info">{t("teacherApply.form.canCreate")}</Notice>}
      {rejected && !revoked && (
        <Notice tone="info">
          {t("teacherApply.form.rejected")}
          {rejected.reason && <> <strong>{t("teacherRequest.reason")}:</strong> {rejected.reason}</>}
        </Notice>
      )}
      <form onSubmit={(e) => void submit(e)} noValidate className="space-y-4">
        <Input id={fieldId("name")} label={t("teacherApply.field.name")} autoComplete="name" required maxLength={TEXT_MAX} value={name}
          error={fieldError("name")} onChange={(e) => { setName(e.target.value); clear("name"); }} />
        <Input id={fieldId("school")} label={t("teacherApply.field.school")} autoComplete="organization" required maxLength={TEXT_MAX} value={school}
          hint={t("teacherApply.field.schoolHint")} error={fieldError("school")} onChange={(e) => { setSchool(e.target.value); clear("school"); }} />
        <Input id={fieldId("subject")} label={t("teacherApply.field.subject")} required maxLength={TEXT_MAX} value={subject}
          error={fieldError("subject")} onChange={(e) => { setSubject(e.target.value); clear("subject"); }} />
        <Input id={fieldId("phone")} label={t("teacherApply.field.phone")} type="tel" autoComplete="tel" required maxLength={PHONE_MAX} value={phone}
          placeholder={t("auth.phonePlaceholder")} hint={t("teacherApply.field.phoneHint")} error={fieldError("phone")}
          onChange={(e) => { setPhone(e.target.value); clear("phone"); }} />
        <Textarea id="apply-message" label={t("teacherApply.field.message")} optional rows={3} maxLength={MESSAGE_MAX} value={message}
          onChange={(e) => setMessage(e.target.value)} />
        {needsAge && (
          <div>
            <Checkbox id={fieldId("age")} label={t("teacherApply.age")} checked={adult} error={fieldError("age")}
              onChange={(e) => { setAdult(e.target.checked); clear("age"); }} />
            <PolicyAcceptField id={fieldId("policies")} state={policyState} checked={accepted} error={fieldError("policies")}
              onChange={(value) => { setAccepted(value); clear("policies"); }} />
          </div>
        )}
        {serverError && (
          <p role="alert" className="flex items-start gap-2 rounded-xl border border-danger-200 bg-danger-50 p-3 text-sm font-medium text-danger-800">
            <CircleAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 break-words">{serverError}</span>
          </p>
        )}
        <Button type="submit" size="lg" fullWidth loading={busy} disabled={needsAge && !policyState.policies}
          rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
          {t("teacherApply.form.submit")}
        </Button>
      </form>
    </div>
  );
}

function errorText(t: T, error: unknown, lang: string): string {
  const e = error as { code?: string; details?: Record<string, unknown> };
  if (e.code === "reapply_wait") return t("lms.errors.reapply_wait", { date: fmtApiDate(String(e.details?.available_at ?? ""), lang) });
  return apiErrorText(t, error);
}
