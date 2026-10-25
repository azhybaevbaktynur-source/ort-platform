"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  adminCoursePeople, adminDeleteCourse, adminRestoreCourse, adminTransferOwnership, getAdminCourse, relistCourse, unlistCourse,
} from "@/lib/lms/admin";
import type { AdminCourseOut, RosterEntryOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { isSystemAccount } from "@/lib/lms/organizations";
import { fmtApiDateTime } from "@/lib/format";
import {
  Badge, Button, Card, DescriptionList, LoadingState, PageHeader, ReasonDialog, Table, UserPicker, toast, type TableColumn,
} from "@/components/ui";
import { platformUserSearch, type PickedUser } from "@/components/lms/UserPicker";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { CourseStatusBadge, LoadError, OrgError, SystemAccountBadge } from "@/components/lms/org/OrgUi";

type Action = "delete" | "restore" | "unlist" | "relist" | "transfer";

export default function AdminCourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const [course, setCourse] = useState<AdminCourseOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [newOwner, setNewOwner] = useState<PickedUser | null>(null); // Phase 6 S4: UserPicker (admin B1)
  const userSearch = useMemo(() => platformUserSearch(), []);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const [people, setPeople] = useState<RosterEntryOut[] | null>(null);
  const [peopleCursor, setPeopleCursor] = useState<string | null>(null);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [peopleError, setPeopleError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCourse(await getAdminCourse(courseId));
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  const loadPeople = async (next?: string | null) => {
    setPeopleLoading(true);
    setPeopleError(null);
    try {
      const page = await adminCoursePeople(courseId, next);
      setPeople((prev) => (next && prev ? [...prev, ...page.items] : page.items));
      setPeopleCursor(page.next_cursor);
    } catch (e) {
      setPeopleError(e);
    } finally {
      setPeopleLoading(false);
    }
  };

  const coursesCrumb = { label: t("platformAdmin.courses.title"), href: `/${lang}/admin/courses` };
  const courseTitle = course ? pickLocalized(course.title, lang, "en") || course.id : "";
  const toasts: Record<Action, string> = {
    delete: "platformAdmin.toast.courseDeleted", restore: "platformAdmin.toast.courseRestored", unlist: "platformAdmin.toast.courseUnlisted",
    relist: "platformAdmin.toast.courseRelisted", transfer: "platformAdmin.toast.ownerChanged",
  };

  const run = async (reason: string) => {
    if (!action) return;
    setBusy(true);
    setDialogError(null);
    try {
      let updated: AdminCourseOut;
      if (action === "delete") updated = await adminDeleteCourse(courseId, reason);
      else if (action === "restore") updated = await adminRestoreCourse(courseId, reason);
      else if (action === "unlist") updated = await unlistCourse(courseId, reason || undefined);
      else if (action === "relist") updated = await relistCourse(courseId, reason || undefined);
      else if (newOwner) updated = await adminTransferOwnership(courseId, newOwner.id, reason);
      else return;
      toast.success(t(toasts[action], { course: courseTitle, name: newOwner ? newOwner.display_name || newOwner.email : "" }));
      setCourse(updated);
      setAction(null);
      if (action === "transfer") setNewOwner(null);
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  if (error && !course) {
    return (
      <div>
        <PageHeader title={t("platformAdmin.courses.title")} breadcrumbs={crumbs(coursesCrumb, { label: "…" })} />
        <LoadError error={error} onRetry={load} />
      </div>
    );
  }
  if (!course) return <LoadingState label={t("lms.common.loading")} />;

  const isDeleted = !!course.deleted_at;
  const open = (a: Action) => { setDialogError(null); setAction(a); };
  const titles: Record<Action, string> = {
    delete: t("platformAdmin.courses.deleteTitle"), restore: t("platformAdmin.courses.restoreTitle"),
    unlist: t("platformAdmin.courses.unlistTitle"), relist: t("platformAdmin.courses.relistTitle"),
    transfer: t("platformAdmin.courses.transferTitle"),
  };
  const labels: Record<Action, string> = {
    delete: t("platformAdmin.courses.delete"), restore: t("platformAdmin.courses.restore"),
    unlist: t("platformAdmin.courses.unlist"), relist: t("platformAdmin.courses.relist"),
    transfer: t("platformAdmin.courses.transfer"),
  };
  // Phase 6 S4 (admin M4, M5): dialogs name the course and the effect; system owner badge.
  const ownerName = course.owner.display_name || course.owner.email;
  const systemOwner = isSystemAccount(course.owner);
  const bodies: Record<Action, string> = {
    delete: t("organizations.adminCourse.deleteBody", { course: courseTitle, n: course.active_student_count }),
    restore: t("organizations.adminCourse.restoreBody", { course: courseTitle }),
    unlist: t("organizations.adminCourse.unlistBody", { course: courseTitle }),
    relist: t("organizations.adminCourse.relistBody", { course: courseTitle }),
    transfer: t("organizations.adminCourse.transferBody", { course: courseTitle, from: ownerName, to: newOwner ? newOwner.display_name || newOwner.email : "" }),
  };

  const actions = isDeleted ? (
    <Button variant="secondary" onClick={() => open("restore")}>{labels.restore}</Button>
  ) : (
    <>
      {course.unlisted_by_admin_at
        ? <Button variant="secondary" onClick={() => open("relist")}>{labels.relist}</Button>
        : <Button variant="secondary" onClick={() => open("unlist")}>{labels.unlist}</Button>}
      <Button variant="danger" onClick={() => open("delete")}>{labels.delete}</Button>
    </>
  );
  const badges = (
    <span className="flex flex-wrap items-center gap-2">
      <CourseStatusBadge status={course.status} />
      {course.deleted_at && <Badge tone="danger">{t("platformAdmin.courses.deleted")}</Badge>}
      {course.unlisted_by_admin_at && <Badge tone="warning">{t("platformAdmin.courses.unlisted")}</Badge>}
    </span>
  );
  const rosterColumns: TableColumn<RosterEntryOut>[] = [
    {
      key: "user", header: t("platformAdmin.users.user"), primary: true,
      cell: (p) => <>{p.user.display_name || p.user.email}<span className="block break-all text-sm font-normal text-slate-600">{p.user.email}</span></>,
    },
    { key: "role", header: t("platformAdmin.courses.role"), cell: (p) => <>{t(`courses.roles.${p.role}`)}{p.is_owner ? ` (${t("platformAdmin.courses.ownerTag")})` : ""}</> },
    { key: "state", header: t("platformAdmin.courses.status"), cell: (p) => p.state },
  ];

  return (
    <div>
      <PageHeader title={courseTitle} badge={badges} breadcrumbs={crumbs(coursesCrumb, { label: courseTitle })} secondaryActions={actions} />
      {error ? <OrgError error={error} onRetry={load} className="mb-4" /> : null}
      <Card className="mb-6">
        <DescriptionList twoColumns items={[
          {
            key: "owner", term: t("platformAdmin.courses.owner"),
            description: (
              <span className="inline-flex flex-wrap items-center gap-2">
                <Link href={`/${lang}/admin/users/${course.owner.id}`} className="font-medium text-brand-700 hover:underline">{ownerName}</Link>
                {systemOwner && <SystemAccountBadge />}
              </span>
            ),
          },
          { key: "visibility", term: t("platformAdmin.courses.visibility"), description: t(`platformAdmin.courses.visibilityValues.${course.visibility}`) },
          { key: "students", term: t("platformAdmin.courses.students"), description: course.active_student_count },
          { key: "created", term: t("platformAdmin.users.created"), description: fmtApiDateTime(course.created_at, lang) },
          ...(course.unlisted_by_admin_at ? [{ key: "unlisted", term: t("platformAdmin.courses.unlisted"), description: fmtApiDateTime(course.unlisted_by_admin_at, lang) }] : []),
          ...(course.deleted_at ? [{ key: "deleted", term: t("platformAdmin.courses.deleted"), description: fmtApiDateTime(course.deleted_at, lang) }] : []),
        ]} />
      </Card>

      {!isDeleted && (
        <Card className="mb-6" title={t("platformAdmin.courses.transferHeading")} description={t("platformAdmin.courses.transferHint")}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="w-full sm:max-w-md">
              <UserPicker id="new-owner" label={t("platformAdmin.courses.newOwnerId")} value={newOwner} onChange={setNewOwner}
                search={userSearch} excludeIds={[course.owner.id]} />
            </div>
            <Button variant="secondary" disabled={!newOwner} onClick={() => open("transfer")}>{labels.transfer}</Button>
          </div>
        </Card>
      )}

      <Card title={t("platformAdmin.courses.roster")} description={people === null ? t("platformAdmin.courses.rosterAudited") : undefined}>
        {people === null ? (
          <>
            <Button variant="secondary" loading={peopleLoading} onClick={() => void loadPeople()}>{t("platformAdmin.courses.showRoster")}</Button>
            {peopleError ? <OrgError error={peopleError} onRetry={() => void loadPeople()} className="mt-3" /> : null}
          </>
        ) : (
          <>
            <Table
              caption={t("platformAdmin.courses.roster")}
              columns={rosterColumns}
              rows={people}
              rowKey={(p) => p.enrollment_id}
              countText={people.length ? t("shell.list.shown", { n: people.length }) : undefined}
              pagination={{ nextCursor: peopleCursor, onLoadMore: () => void loadPeople(peopleCursor), loading: peopleLoading }}
            />
            {peopleError ? <OrgError error={peopleError} onRetry={() => void loadPeople(peopleCursor)} className="mt-3" /> : null}
          </>
        )}
      </Card>

      <ReasonDialog
        open={!!action} title={action ? titles[action] : ""} object={courseTitle} effect={action ? bodies[action] : ""}
        confirmLabel={action ? labels[action] : ""}
        tone={action === "delete" ? "danger" : "primary"} optional={action === "unlist" || action === "relist"} busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void run(r)} onCancel={() => setAction(null)}
      />
    </div>
  );
}
