"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { getCourse, listPeople, transferOwnership } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { joinCourseAsTeacher, searchOrgMembers } from "@/lib/lms/organizations";
import { CourseDepartmentCard } from "@/components/lms/org/CourseDepartmentCard"; // Phase 9 S5
import { templateTitle } from "@/lib/lms/templates";
import { isStaffCourse, type CourseOut, type RosterEntryOut } from "@/lib/lms/types";
import { fmtApiDate } from "@/lib/format";
import {
  Badge, Button, Card, ConfirmDialog, DescriptionList, LinkButton, LoadingState, PageHeader, UserPicker, toast,
  type PickedUser, type UserSearch,
} from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { CourseStatusBadge, LoadError, OrgError } from "@/components/lms/org/OrgUi";

/** Org admin course summary (design §3): facts, staff, assign owner, open course, join as teacher (A13). */
export default function OrgCourseSummaryPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const { lang, t } = useTranslation();
  const { org, readOnly, crumbs } = useOrg();
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

  const searchMembers: UserSearch = useMemo(() => async (q) => searchOrgMembers(org.id, q), [org.id]);

  const coursesCrumb = { label: t("organizations.org.nav.courses"), href: `/${lang}/org/${org.id}/courses` };
  if (error && !course) {
    return (
      <div>
        <PageHeader title={t("organizations.courses.title")} breadcrumbs={crumbs(coursesCrumb, { label: "…" })} />
        <LoadError error={error} onRetry={load} />
      </div>
    );
  }
  if (!course) return <LoadingState label={t("lms.common.loading")} />;

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
    <div>
      <PageHeader
        title={title}
        badge={<CourseStatusBadge status={course.status} />}
        breadcrumbs={crumbs(coursesCrumb, { label: title })}
        primaryAction={<LinkButton href={`/${lang}/courses/${course.id}`}>{t("organizations.course.open")}</LinkButton>}
        secondaryActions={!iAmTeacher ? (
          <Button variant="secondary" disabled={readOnly} onClick={() => { setDialogError(null); setDialog("join"); }}>
            {t("organizations.course.join")}
          </Button>
        ) : undefined}
      />
      <div className="space-y-6">
        <Card title={t("organizations.course.facts")}>
          <DescriptionList twoColumns items={[
            { key: "owner", term: t("organizations.courses.owner"), description: ownerName },
            { key: "template", term: t("templates.field"), description: tpl ? templateTitle(t, tpl.key, tpl.title_key) : t("templates.general") },
            ...(staffOut ? [
              { key: "students", term: t("organizations.counts.students"), description: staffOut.active_student_count },
              { key: "created", term: t("organizations.course.created"), description: fmtApiDate(staffOut.created_at, lang) },
            ] : []),
            { key: "languages", term: t("organizations.course.languages"), description: course.languages.map((l) => t(`courses.languages.${l}`)).join(", ") },
          ]} />
        </Card>
        <Card title={t("organizations.course.staff")} padding={staff && staff.length > 0 ? "none" : "md"}>
          {staffError ? <OrgError error={staffError} onRetry={loadStaff} /> : staff === null ? <LoadingState label={t("lms.common.loading")} rows={1} /> : staff.length === 0 ? (
            <p className="text-sm text-slate-600">{t("organizations.course.noStaff")}</p>
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {staff.map((s) => (
                <li key={s.enrollment_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-6">
                  <span className="min-w-0">
                    <span className="block break-words font-medium text-slate-900">{s.user.display_name || s.user.email}</span>
                    <span className="block break-all text-sm text-slate-600">{s.user.email}</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
                    {t(`courses.roles.${s.role}`)}
                    {s.is_owner && <Badge tone="info">{t("organizations.course.ownerTag")}</Badge>}
                    {s.source === "org_admin_self" && <Badge tone="warning">{t("organizations.course.joinedAsAdmin")}</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {/* Phase 9 S5: the course's department (PATCH /org/{org}/courses/{id}) */}
        <CourseDepartmentCard orgId={org.id} courseId={course.id} current={course.organization_id ?? ""} readOnly={readOnly}
          onMoved={() => void load()} />
        <Card title={t("organizations.course.assignOwner")} description={t("organizations.course.assignOwnerHint")}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1">
              <UserPicker label={t("organizations.course.newOwner")} value={newOwner} onChange={setNewOwner}
                search={searchMembers} excludeIds={owner ? [owner.id] : []} disabled={readOnly} />
            </div>
            <Button variant="secondary" disabled={!newOwner || readOnly} onClick={() => { setDialogError(null); setDialog("owner"); }}>
              {t("organizations.course.assignOwner")}
            </Button>
          </div>
        </Card>
      </div>
      <ConfirmDialog
        open={dialog !== null}
        title={dialog === "join" ? t("organizations.course.joinTitle", { course: title }) : t("organizations.course.ownerTitle", { course: title })}
        object={title}
        effect={dialog === "join"
          ? t("organizations.course.joinBody")
          : t("organizations.course.ownerBody", { course: title, from: ownerName, to: newOwner ? newOwner.display_name || newOwner.email : "" })}
        confirmLabel={dialog === "join" ? t("organizations.course.join") : t("organizations.course.assignOwner")}
        busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={() => void confirm()} onCancel={() => setDialog(null)}
      />
    </div>
  );
}
