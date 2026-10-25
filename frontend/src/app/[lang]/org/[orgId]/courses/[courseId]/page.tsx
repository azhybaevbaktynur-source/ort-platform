"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getCourse, listPeople, transferOwnership } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { joinCourseAsTeacher, listOrgMembers } from "@/lib/lms/organizations";
import { templateTitle } from "@/lib/lms/templates";
import { isStaffCourse, type CourseOut, type RosterEntryOut } from "@/lib/lms/types";
import { fmtApiDate } from "@/lib/format";
import { StatusBadge } from "@/components/lms/CourseCard";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { UserPicker, type PickedUser, type UserSearch } from "@/components/lms/UserPicker";
import { useOrg } from "@/components/lms/org/OrgShell";
import { Loading, OrgError, btn, cardCls } from "@/components/lms/org/OrgUi";
import { toast } from "@/components/ui/Toast";

/** Org admin course summary (design §3): facts, staff, assign owner, open course, join as teacher (A13). */
export default function OrgCourseSummaryPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const { lang, t } = useTranslation();
  const { org, readOnly } = useOrg();
  const [course, setCourse] = useState<CourseOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [staff, setStaff] = useState<RosterEntryOut[] | null>(null);
  const [staffError, setStaffError] = useState<unknown>(null);
  const [newOwner, setNewOwner] = useState<PickedUser | null>(null);
  const [dialog, setDialog] = useState<"owner" | "join" | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCourse(await getCourse(courseId));
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  const loadStaff = useCallback(async () => {
    setStaffError(null);
    try {
      const [teachers, assistants] = await Promise.all([
        listPeople(courseId, { role: "teacher", state: "active", limit: 50 }),
        listPeople(courseId, { role: "assistant", state: "active", limit: 50 }),
      ]);
      const rows = [...teachers.items, ...assistants.items].filter((r): r is RosterEntryOut => "enrollment_id" in r);
      setStaff(rows);
    } catch (e) {
      setStaffError(e);
    }
  }, [courseId]);
  useEffect(() => { void load(); void loadStaff(); }, [load, loadStaff]);

  const searchMembers: UserSearch = useMemo(() => async (q) => {
    const page = await listOrgMembers(org.id, { q, state: "active", limit: 10 });
    return page.items.filter((m) => !m.disabled).map((m) => ({ id: m.user_id, display_name: m.display_name, email: m.email }));
  }, [org.id]);

  const back = <Link href={`/${lang}/org/${org.id}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("organizations.courses.back")}</Link>;
  if (error && !course) return <div className="space-y-3">{back}<OrgError error={error} onRetry={load} /></div>;
  if (!course) return <Loading />;

  const title = pickLocalized(course.title, lang, course.default_language) || course.id;
  const staffOut = isStaffCourse(course) ? course : null;
  const owner = staffOut?.owner ?? null;
  const ownerName = owner ? owner.display_name || owner.email : course.owner_display_name || "—";
  const myRole = course.my_enrollment?.role;
  const iAmTeacher = myRole === "teacher" && course.my_enrollment?.state === "active";
  const tpl = course.template;

  const confirm = async () => {
    setBusy(true);
    setDialogError(null);
    try {
      if (dialog === "owner" && newOwner) {
        await transferOwnership(course.id, newOwner.id);
        toast.success(t("organizations.course.ownerChanged", { name: newOwner.display_name || newOwner.email }));
        setNewOwner(null);
      } else if (dialog === "join") {
        await joinCourseAsTeacher(org.id, course.id);
        toast.success(t("organizations.course.joined"));
      }
      setDialog(null);
      await Promise.all([load(), loadStaff()]);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        {back}
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-bold text-slate-900">{title}</h2>
          <StatusBadge status={course.status} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href={`/${lang}/courses/${course.id}`} className={btn.primary}>{t("organizations.course.open")}</Link>
        {!iAmTeacher && (
          <button type="button" className={btn.secondary} disabled={readOnly} onClick={() => { setDialogError(null); setDialog("join"); }}>
            {t("organizations.course.join")}
          </button>
        )}
      </div>
      <section className={cardCls} aria-labelledby="oc-facts">
        <h3 id="oc-facts" className="mb-3 font-semibold text-slate-900">{t("organizations.course.facts")}</h3>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-slate-500">{t("organizations.courses.owner")}</dt><dd>{ownerName}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("templates.field")}</dt><dd>{tpl ? templateTitle(t, tpl.key, tpl.title_key) : t("templates.general")}</dd></div>
          {staffOut && <div><dt className="text-xs text-slate-500">{t("organizations.counts.students")}</dt><dd>{staffOut.active_student_count}</dd></div>}
          {staffOut && <div><dt className="text-xs text-slate-500">{t("organizations.course.created")}</dt><dd>{fmtApiDate(staffOut.created_at, lang)}</dd></div>}
          <div><dt className="text-xs text-slate-500">{t("organizations.course.languages")}</dt><dd>{course.languages.map((l) => t(`courses.languages.${l}`)).join(", ")}</dd></div>
        </dl>
      </section>
      <section className={cardCls} aria-labelledby="oc-staff">
        <h3 id="oc-staff" className="mb-3 font-semibold text-slate-900">{t("organizations.course.staff")}</h3>
        {staffError ? <OrgError error={staffError} onRetry={loadStaff} /> : staff === null ? <Loading /> : staff.length === 0 ? (
          <p className="text-sm text-slate-500">{t("organizations.course.noStaff")}</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {staff.map((s) => (
              <li key={s.enrollment_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="block truncate font-medium text-slate-900">{s.user.display_name || s.user.email}</span>
                  <span className="block truncate text-xs text-slate-500">{s.user.email}</span>
                </span>
                <span className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                  {t(`courses.roles.${s.role}`)}
                  {s.is_owner && <span className="rounded-full bg-brand-50 px-2 py-0.5 font-semibold text-brand-700">{t("organizations.course.ownerTag")}</span>}
                  {s.source === "org_admin_self" && <span className="rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-900">{t("organizations.course.joinedAsAdmin")}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className={cardCls} aria-labelledby="oc-owner">
        <h3 id="oc-owner" className="mb-1 font-semibold text-slate-900">{t("organizations.course.assignOwner")}</h3>
        <p className="mb-3 text-sm text-slate-600">{t("organizations.course.assignOwnerHint")}</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <UserPicker label={t("organizations.course.newOwner")} value={newOwner} onChange={setNewOwner}
              search={searchMembers} excludeIds={owner ? [owner.id] : []} disabled={readOnly} />
          </div>
          <button type="button" className={btn.secondary} disabled={!newOwner || readOnly} onClick={() => { setDialogError(null); setDialog("owner"); }}>
            {t("organizations.course.assignOwner")}
          </button>
        </div>
      </section>
      <ConfirmDialog
        open={dialog !== null}
        title={dialog === "join" ? t("organizations.course.joinTitle", { course: title }) : t("organizations.course.ownerTitle", { course: title })}
        body={dialog === "join"
          ? t("organizations.course.joinBody")
          : t("organizations.course.ownerBody", { course: title, from: ownerName, to: newOwner ? newOwner.display_name || newOwner.email : "" })}
        confirmLabel={dialog === "join" ? t("organizations.course.join") : t("organizations.course.assignOwner")}
        busy={busy} error={dialogError} onConfirm={() => void confirm()} onCancel={() => setDialog(null)}
      />
    </div>
  );
}
