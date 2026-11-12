"use client";

// Step 3b S2 (CATALOG_AND_TEACHERS_DESIGN 2.4): Admin → Каталог. One tab per listing state (`GET /platform/catalog?state=`,
// paginated): requests (oldest first), listed, declined, blocked. Row: course, teacher (person page) and kind, how to
// join, content, students, the date, the content-changed marker. Actions: open the landing as students see it, approve
// (a listed course with the marker: re-check), decline (a note is required: course staff see it, students never),
// block / relist (the Admin → Courses unlist / relist routes). The server decides every transition.
import React, { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { approveListing, declineListing, listAdminCatalog, relistCourse, unlistCourse, type AdminCatalogState } from "@/lib/lms/admin";
import type { AdminCatalogRowOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Badge, Button, EmptyState, LinkButton, OverflowMenu, PageHeader, ReasonDialog, STAFF_WIDTH, TabPanel, Table, Tabs, toast, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { OrgError } from "@/components/lms/org/OrgUi";

const STATES: AdminCatalogState[] = ["pending", "listed", "declined", "blocked"];
type DialogKind = "decline" | "block" | "relist";

function asState(v: string | null): AdminCatalogState {
  return STATES.includes(v as AdminCatalogState) ? (v as AdminCatalogState) : "pending";
}

function AdminCatalog() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const router = useRouter();
  const params = useSearchParams();
  const [state, setStateRaw] = useState<AdminCatalogState>(() => asState(params.get("state")));
  const setState = (s: AdminCatalogState) => {
    setStateRaw(s);
    router.replace(s === "pending" ? `/${lang}/admin/catalog` : `/${lang}/admin/catalog?state=${s}`, { scroll: false });
  };
  const fetchPage = useCallback((cursor: string | null) => listAdminCatalog(state, cursor), [state]);
  const list = useCursorList(fetchPage);
  const table = useTableState(list);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<{ kind: DialogKind; row: AdminCatalogRowOut } | null>(null);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const titleOf = (r: AdminCatalogRowOut) => pickLocalized(r.title, lang, r.default_language) || r.id;
  const nameOf = (r: AdminCatalogRowOut) => r.owner.display_name || r.owner.email;
  const landingOpen = (r: AdminCatalogRowOut) => r.status === "published" && r.visibility === "catalog" && r.listing.state !== "blocked";

  const approve = async (r: AdminCatalogRowOut) => {
    setBusyId(r.id);
    setActionError(null);
    try {
      const recheck = r.listing.state === "listed";
      await approveListing(r.id);
      toast.success(t(recheck ? "platformAdmin.catalog.toast.rechecked" : "platformAdmin.catalog.toast.approved", { course: titleOf(r) }));
      await list.reload();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusyId(null);
    }
  };

  const confirm = async (text: string) => {
    if (!dialog) return;
    const { kind, row } = dialog;
    setBusyId(row.id);
    setDialogError(null);
    try {
      if (kind === "decline") await declineListing(row.id, text);
      else if (kind === "block") await unlistCourse(row.id, text || undefined);
      else await relistCourse(row.id, text || undefined);
      toast.success(t(`platformAdmin.catalog.toast.${kind === "decline" ? "declined" : kind === "block" ? "blocked" : "relisted"}`, { course: titleOf(row) }));
      setDialog(null);
      await list.reload();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusyId(null);
    }
  };

  const teacherKind = (r: AdminCatalogRowOut) => r.teacher_kind === "school" ? (r.school_name || t("platformAdmin.catalog.school"))
    : t(r.teacher_kind === "platform" ? "platformAdmin.catalog.platform" : "platformAdmin.catalog.independent");
  const dateOf = (r: AdminCatalogRowOut) => fmtApiDateTimeShort(state === "pending" ? r.listing.requested_at : r.listing.decided_at, lang) || "—";

  const columns: TableColumn<AdminCatalogRowOut>[] = [
    {
      key: "course", header: t("platformAdmin.catalog.columns.course"), primary: true,
      cell: (r) => (
        <span className="flex min-w-0 items-start gap-3">
          {r.cover_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={r.cover_url} alt="" loading="lazy" decoding="async" className="hidden h-10 w-16 shrink-0 rounded-md object-cover sm:block" />
          )}
          <span className="min-w-0">
            <Link href={`/${lang}/admin/courses/${r.id}`} className="break-words font-semibold text-brand-700 hover:underline">{titleOf(r)}</Link>
            {r.listing.content_changed && (
              <span className="mt-1 block"><Badge tone="warning">{t("platformAdmin.catalog.changedSince")}</Badge></span>
            )}
            {r.listing.state === "declined" && r.listing.note && (
              <span className="mt-1 block whitespace-pre-wrap break-words text-sm font-normal text-slate-600">{t("platformAdmin.catalog.note", { note: r.listing.note })}</span>
            )}
          </span>
        </span>
      ),
    },
    {
      key: "teacher", header: t("platformAdmin.catalog.columns.teacher"),
      cell: (r) => (
        <span className="block text-right sm:text-left">
          <Link href={`/${lang}/admin/users/${r.owner.id}`} className="break-words font-medium text-brand-700 hover:underline">{nameOf(r)}</Link>
          <span className="block text-sm text-slate-600">{teacherKind(r)}</span>
        </span>
      ),
    },
    { key: "mode", header: t("platformAdmin.catalog.columns.mode"), cell: (r) => t(`catalog.modes.${r.enrollment_mode}`) },
    {
      key: "content", header: t("platformAdmin.catalog.columns.content"),
      cell: (r) => (
        <span className="text-sm">
          <span className="block whitespace-nowrap">{t("platformAdmin.catalog.tests", { n: r.tests_count })}</span>
          <span className="block whitespace-nowrap">{t("platformAdmin.catalog.lessons", { n: r.lessons_count })}</span>
          <span className="block whitespace-nowrap text-slate-600">{t("platformAdmin.catalog.students", { n: r.student_count })}</span>
        </span>
      ),
    },
    { key: "date", header: t(state === "pending" ? "platformAdmin.catalog.columns.requested" : "platformAdmin.catalog.columns.decided"), nowrap: true, cell: dateOf },
    {
      key: "actions", header: <span className="sr-only">{t("platformAdmin.catalog.columns.actions")}</span>, label: t("platformAdmin.catalog.columns.actions"),
      actions: true, align: "right",
      cell: (r) => {
        const s = r.listing.state;
        const more = [
          ...(s === "pending" ? [{ id: "decline", label: t("platformAdmin.catalog.decline"), danger: true }] : []),
          ...(s !== "blocked" ? [{ id: "block", label: t("platformAdmin.catalog.block"), danger: true }] : []),
          { id: "course", label: t("platformAdmin.catalog.openCourse") },
        ];
        return (
          <span className="inline-flex flex-wrap items-center justify-end gap-2">
            {landingOpen(r) && (
              <LinkButton size="sm" variant="secondary" href={`/${lang}/courses/catalog/${r.id}`}>{t("platformAdmin.catalog.open")}</LinkButton>
            )}
            {(s === "pending" || (s === "listed" && r.listing.content_changed)) && (
              <Button size="sm" loading={busyId === r.id && !dialog} disabled={busyId === r.id} onClick={() => void approve(r)}>
                {t(s === "pending" ? "platformAdmin.catalog.approve" : "platformAdmin.catalog.recheck")}
              </Button>
            )}
            {s === "blocked" && (
              <Button size="sm" variant="secondary" disabled={busyId === r.id} onClick={() => { setDialogError(null); setDialog({ kind: "relist", row: r }); }}>
                {t("platformAdmin.catalog.relist")}
              </Button>
            )}
            <OverflowMenu label={t("platformAdmin.catalog.more", { course: titleOf(r) })} groups={[{ id: "r", items: more }]}
              onSelect={(id) => {
                if (id === "course") router.push(`/${lang}/admin/courses/${r.id}`);
                else { setDialogError(null); setDialog({ kind: id as DialogKind, row: r }); }
              }} />
          </span>
        );
      },
    },
  ];

  const tabsId = "admin-catalog";
  const d = dialog;
  const dialogText = d ? {
    decline: { title: "platformAdmin.catalog.declineTitle", body: "platformAdmin.catalog.declineBody", confirm: "platformAdmin.catalog.decline" },
    block: { title: "platformAdmin.catalog.blockTitle", body: "platformAdmin.catalog.blockBody", confirm: "platformAdmin.catalog.block" },
    relist: { title: "platformAdmin.catalog.relistTitle", body: "platformAdmin.catalog.relistBody", confirm: "platformAdmin.catalog.relist" },
  }[d.kind] : null;
  return (
    <div className={`w-full ${STAFF_WIDTH.list}`}>
      <PageHeader title={t("platformAdmin.catalog.title")} description={t("platformAdmin.catalog.subtitle")} breadcrumbs={crumbs({ label: t("platformAdmin.catalog.title") })} />
      <Tabs id={tabsId} label={t("platformAdmin.catalog.tabsLabel")} value={state} onChange={(v) => setState(v as AdminCatalogState)}
        items={STATES.map((s) => ({ id: s, label: t(`platformAdmin.catalog.tabs.${s}`) }))} />
      <TabPanel tabsId={tabsId} value={state}>
        {actionError ? <OrgError error={actionError} className="mb-4" /> : null}
        <Table caption={t(`platformAdmin.catalog.tabs.${state}`)} density="compact" columns={columns} rows={list.items} rowKey={(r) => r.id} {...table}
          empty={<EmptyState variant="plain" title={t(`platformAdmin.catalog.empty.${state}`)} />} />
        <MoreError list={list} />
      </TabPanel>
      <ReasonDialog
        open={!!d}
        title={dialogText ? t(dialogText.title) : ""}
        object={d ? `${titleOf(d.row)} · ${nameOf(d.row)}` : undefined}
        effect={d && dialogText ? t(dialogText.body, { course: titleOf(d.row) }) : ""}
        confirmLabel={dialogText ? t(dialogText.confirm) : ""}
        tone={d?.kind === "relist" ? "primary" : "danger"}
        optional={d?.kind !== "decline"}
        reasonLabel={d?.kind === "decline" ? t("platformAdmin.catalog.declineNote") : undefined}
        reasonHint={d?.kind === "decline" ? t("platformAdmin.catalog.declineNoteHint") : undefined}
        busy={!!busyId}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(text) => void confirm(text)} onCancel={() => setDialog(null)}
      />
    </div>
  );
}

export default function AdminCatalogPage() {
  return (
    <Suspense fallback={null}>
      <AdminCatalog />
    </Suspense>
  );
}
