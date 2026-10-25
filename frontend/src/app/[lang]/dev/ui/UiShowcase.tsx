"use client";

import React, { useMemo, useState } from "react";
import { BookOpen, CircleCheck, Clock, GraduationCap, Pencil, Plus, Settings, ShieldCheck, Trash, TriangleAlert, Trophy, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  Badge, Button, Card, Checkbox, ConfirmDialog, DescriptionList, Dialog, EmptyState, ErrorState, FilterBar, IconButton, Input,
  LinkButton, LoadingState, PageHeader, ReasonDialog, Select, Skeleton, SkeletonText, StatTile, Switch, Table, TabPanel, Tabs,
  TabsNav, Textarea, UserPicker, useToast, type BadgeTone, type PickedUser, type TableColumn, type TableSort,
} from "@/components/ui";

/* Demo data (names and emails are sample data, not UI strings). */
type Status = "published" | "inProgress" | "late" | "notPassed" | "draft";
interface Student { id: string; name: string; email: string; status: Status; score: number | null; joined: string }

const STUDENTS: Student[] = [
  { id: "1", name: "Айжан Абдыкалыкова", email: "aizhan.abdykalykova@school5.kg", status: "published", score: 186, joined: "2026-09-02" },
  { id: "2", name: "Бектур Жумабеков", email: "bektur.zh@school5.kg", status: "inProgress", score: null, joined: "2026-09-03" },
  { id: "3", name: "Нурайым Осмонова", email: "nuraiym@mail.kg", status: "late", score: 142, joined: "2026-09-05" },
  { id: "4", name: "Эрлан Токтосунов", email: "erlan.t@school5.kg", status: "notPassed", score: 98, joined: "2026-09-10" },
  { id: "5", name: "Алина Ким", email: "alina.kim@school5.kg", status: "published", score: 201, joined: "2026-09-12" },
  { id: "6", name: "Тимур Асанов", email: "timur.asanov@school5.kg", status: "draft", score: null, joined: "2026-09-15" },
  { id: "7", name: "Мээрим Сыдыкова", email: "meerim.s@school5.kg", status: "published", score: 167, joined: "2026-09-20" },
  { id: "8", name: "Данияр Мамытов", email: "daniyar.m@school5.kg", status: "inProgress", score: null, joined: "2026-10-01" },
];
const PEOPLE: PickedUser[] = STUDENTS.map((s) => ({ id: s.id, display_name: s.name, email: s.email }));

const STATUS_TONE: Record<Status, BadgeTone> = { published: "success", inProgress: "info", late: "warning", notPassed: "danger", draft: "neutral" };
const STATUS_ICON: Record<Status, React.ReactNode> = {
  published: <CircleCheck aria-hidden="true" />, inProgress: <Clock aria-hidden="true" />, late: <TriangleAlert aria-hidden="true" />,
  notPassed: <TriangleAlert aria-hidden="true" />, draft: <Pencil aria-hidden="true" />,
};

const SWATCHES: { name: string; cls: string[] }[] = [
  { name: "brand", cls: ["bg-brand-50", "bg-brand-100", "bg-brand-200", "bg-brand-500", "bg-brand-600", "bg-brand-700", "bg-brand-900"] },
  { name: "slate", cls: ["bg-slate-50", "bg-slate-100", "bg-slate-200", "bg-slate-400", "bg-slate-600", "bg-slate-700", "bg-slate-900"] },
  { name: "success", cls: ["bg-success-50", "bg-success-100", "bg-success-200", "bg-success-500", "bg-success-600", "bg-success-700", "bg-success-800"] },
  { name: "warning", cls: ["bg-warning-50", "bg-warning-100", "bg-warning-200", "bg-warning-500", "bg-warning-600", "bg-warning-700", "bg-warning-900"] },
  { name: "danger", cls: ["bg-danger-50", "bg-danger-100", "bg-danger-200", "bg-danger-500", "bg-danger-600", "bg-danger-700", "bg-danger-800"] },
  { name: "gold", cls: ["bg-gold-50", "bg-gold-100", "bg-gold-200", "bg-gold-400", "bg-gold-500", "bg-gold-600", "bg-gold-800"] },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-4">
      <h2 id={`${id}-h`} className="mb-3 text-lg font-semibold leading-7 text-slate-900">{title}</h2>
      {children}
    </section>
  );
}

export function UiShowcase() {
  const { t, lang } = useTranslation();
  const { toast } = useToast();
  const d = (k: string, p?: Record<string, string | number>) => t(`ui.demo.${k}`, p);

  // fields
  const [late, setLate] = useState(true);
  const [emails, setEmails] = useState(false);
  const [emailsBusy, setEmailsBusy] = useState(false);
  // tabs
  const [tab, setTab] = useState("people");
  // table
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sort, setSort] = useState<TableSort | null>({ key: "name", direction: "asc" });
  const [shown, setShown] = useState(5);
  const [moreLoading, setMoreLoading] = useState(false);
  const [view, setView] = useState("data");
  // dialogs
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [reasonOpen, setReasonOpen] = useState(false);
  // picker
  const [picked, setPicked] = useState<PickedUser | null>(null);

  // Fixed DD.MM.YYYY so server and browser render the same text (sample data only).
  const fmtDate = (iso: string) => iso.split("-").reverse().join(".");
  const statusLabel = (s: Status) => d(`badge.${s}`);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    let rows = STUDENTS.filter((s) => (!term || s.name.toLowerCase().includes(term) || s.email.includes(term)) && (!statusFilter || s.status === statusFilter));
    if (sort) {
      const dir = sort.direction === "asc" ? 1 : -1;
      rows = [...rows].sort((a, b) => {
        const av = a[sort.key as keyof Student] ?? -1;
        const bv = b[sort.key as keyof Student] ?? -1;
        return (typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv))) * dir;
      });
    }
    return rows;
  }, [q, statusFilter, sort]);
  const pageRows = filtered.slice(0, shown);

  const columns: TableColumn<Student>[] = [
    { key: "name", header: d("table.name"), primary: true, sortable: true, cell: (s) => s.name },
    { key: "email", header: d("table.email"), hideOnMobile: true, cell: (s) => <span className="text-slate-700">{s.email}</span> },
    { key: "status", header: d("table.status"), mobilePriority: 0, cell: (s) => <Badge tone={STATUS_TONE[s.status]} icon={STATUS_ICON[s.status]}>{statusLabel(s.status)}</Badge> },
    { key: "score", header: d("table.score"), sortable: true, align: "right", nowrap: true, mobilePriority: 1, cell: (s) => (s.score === null ? "—" : s.score) },
    { key: "joined", header: d("table.joined"), sortable: true, nowrap: true, cell: (s) => fmtDate(s.joined) },
    { key: "actions", header: "", actions: true, align: "right", cell: (s) => (
      <span className="inline-flex gap-1">
        <Button size="sm" variant="secondary" onClick={() => toast.info(s.name)}>{d("table.open")}</Button>
        <IconButton aria-label={`${d("b.remove")}: ${s.name}`} variant="danger" icon={<Trash />} onClick={() => setConfirmOpen(true)} />
      </span>
    ) },
  ];

  const tabItems = [
    { id: "home", label: d("tabs.home") },
    { id: "people", label: d("tabs.people"), count: 28 },
    { id: "assessments", label: d("tabs.assessments"), count: 6 },
    { id: "grades", label: d("tabs.grades") },
    { id: "bank", label: d("tabs.bank") },
    { id: "files", label: d("tabs.files") },
    { id: "announcements", label: d("tabs.announcements"), disabled: true },
    { id: "settings", label: d("tabs.settings") },
  ];

  const search = async (term: string) => {
    await new Promise((r) => setTimeout(r, 400));
    const x = term.toLowerCase();
    return PEOPLE.filter((p) => (p.display_name ?? "").toLowerCase().includes(x) || p.email.includes(x));
  };

  return (
    <main className="mx-auto max-w-5xl space-y-10 px-4 py-6 sm:px-6 sm:py-10">
      <PageHeader title={d("title")} description={d("intro")} />

      <Section id="tokens" title={d("s.tokens")}>
        <div className="grid gap-3 sm:grid-cols-2">
          {SWATCHES.map((s) => (
            <div key={s.name} className="rounded-2xl border border-slate-200 bg-white p-3">
              <p className="mb-2 font-mono text-sm text-slate-700">{s.name}-*</p>
              <div className="grid grid-cols-7 gap-1">
                {s.cls.map((c) => <span key={c} title={c} className={`h-8 rounded-lg border border-slate-200 ${c}`} />)}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-2xl font-bold leading-8 text-slate-900">{d("card.title")} — text-2xl</p>
          <p className="text-lg font-semibold leading-7 text-slate-900">{d("s.cards")} — text-lg</p>
          <p className="text-base leading-6 text-slate-800">{d("dl.visibilityValue")} — text-base</p>
          <p className="text-sm leading-6 text-slate-600">{d("f.titleHint")} — text-sm</p>
        </div>
      </Section>

      <Section id="buttons" title={d("s.buttons")}>
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <Button>{d("b.save")}</Button>
            <Button variant="secondary">{t("ui.cancel")}</Button>
            <Button variant="danger">{d("b.delete")}</Button>
            <Button variant="link">{d("b.details")}</Button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button size="sm">{d("b.small")}</Button>
            <Button size="sm" variant="secondary">{d("b.small")}</Button>
            <Button size="lg">{d("b.large")}</Button>
            <Button leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />} variant="secondary">{d("b.add")}</Button>
            <LinkButton href={`/${lang}/courses`} variant="secondary" leftIcon={<BookOpen aria-hidden="true" className="h-4 w-4" />}>{d("b.toCatalog")}</LinkButton>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button loading>{d("b.save")}</Button>
            <Button loading variant="secondary">{d("b.save")}</Button>
            <Button loading variant="danger">{d("b.delete")}</Button>
            <Button disabled>{d("b.disabled")}</Button>
            <Button disabled variant="secondary">{d("b.disabled")}</Button>
          </div>
          <p className="mt-2 text-sm text-slate-600">{d("b.loadingNote")}</p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <IconButton aria-label={d("b.edit")} icon={<Pencil />} />
            <IconButton aria-label={d("b.settings")} icon={<Settings />} variant="secondary" />
            <IconButton aria-label={d("b.remove")} icon={<Trash />} variant="danger" />
            <IconButton aria-label={d("b.save")} icon={<Pencil />} loading />
          </div>
          <div className="mt-4 max-w-sm"><Button fullWidth>{d("b.large")}</Button></div>
        </Card>
      </Section>

      <Section id="fields" title={d("s.fields")}>
        <Card>
          <div className="grid gap-5 sm:grid-cols-2">
            <Input label={d("f.title")} hint={d("f.titleHint")} defaultValue={d("card.title")} required />
            <Input label={d("f.email")} type="email" defaultValue="aizhan@" error={d("f.emailError")} />
            <Input label={d("f.subtitle")} optional placeholder={d("card.body")} />
            <Input label={d("f.code")} defaultValue="ALG-9A-7Q" disabled />
            <Textarea label={d("f.description")} hint={d("f.descriptionHint")} containerClassName="sm:col-span-2" />
            <Select label={d("f.language")} placeholder={d("f.languagePlaceholder")} defaultValue="ky"
              options={[{ value: "ky", label: d("f.ky") }, { value: "ru", label: d("f.ru") }, { value: "en", label: d("f.en") }]} />
            <Select label={d("f.language")} placeholder={d("f.languagePlaceholder")} defaultValue="" error={d("f.languageError")}
              options={[{ value: "ky", label: d("f.ky") }, { value: "ru", label: d("f.ru") }]} />
          </div>
          <div className="mt-5 grid gap-x-8 gap-y-2 sm:grid-cols-2">
            <div>
              <Checkbox label={d("f.catalog")} hint={d("f.catalogHint")} defaultChecked />
              <Checkbox label={d("f.rules")} error={d("f.rulesError")} />
              <Checkbox label={d("f.ortScoring")} disabled defaultChecked />
            </div>
            <div>
              <Switch label={d("f.late")} hint={d("f.lateHint")} checked={late} onChange={setLate} />
              <Switch label={d("f.emails")} checked={emails} busy={emailsBusy}
                onChange={(v) => { setEmailsBusy(true); setTimeout(() => { setEmails(v); setEmailsBusy(false); }, 800); }} />
              <Switch label={d("f.ortScoring")} checked disabled onChange={() => undefined} />
            </div>
          </div>
        </Card>
      </Section>

      <Section id="badges" title={d("s.badges")}>
        <Card>
          <div className="flex flex-wrap gap-2">
            <Badge>{d("badge.draft")}</Badge>
            <Badge tone="info" icon={<Clock aria-hidden="true" />}>{d("badge.inProgress")}</Badge>
            <Badge tone="success" icon={<CircleCheck aria-hidden="true" />}>{d("badge.published")}</Badge>
            <Badge tone="warning" icon={<TriangleAlert aria-hidden="true" />}>{d("badge.late")}</Badge>
            <Badge tone="danger">{d("badge.notPassed")}</Badge>
            <Badge tone="system" icon={<ShieldCheck aria-hidden="true" />}>{d("badge.system")}</Badge>
          </div>
        </Card>
      </Section>

      <Section id="cards" title={d("s.cards")}>
        <div className="space-y-4">
          <Card title={d("card.title")} description={d("card.description")}
            actions={<LinkButton href={`/${lang}/courses`} variant="secondary" size="sm">{d("card.open")}</LinkButton>}>
            <p className="text-base leading-6 text-slate-700 sm:text-sm sm:leading-6">{d("card.body")}</p>
          </Card>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label={d("stat.students")} value="28" icon={<Users />} />
            <StatTile label={d("stat.review")} value="5" hint={d("stat.reviewHint")} icon={<GraduationCap />} href={`/${lang}/courses`} />
            <StatTile label={d("stat.best")} value="201" hint={d("stat.bestHint")} icon={<Trophy />} tone="gold" />
          </div>
          <Card>
            <DescriptionList twoColumns items={[
              { term: d("dl.owner"), description: "Айбек Токтогулов" },
              { term: d("dl.created"), description: fmtDate("2026-09-01") },
              { term: d("dl.language"), description: d("f.ky") },
              { term: d("dl.visibility"), description: d("dl.visibilityValue") },
            ]} />
          </Card>
          <Card>
            <DescriptionList layout="columns" items={[
              { term: d("dl.owner"), description: "Айбек Токтогулов" },
              { term: d("dl.visibility"), description: d("dl.visibilityValue") },
            ]} />
          </Card>
        </div>
      </Section>

      <Section id="header" title={d("s.header")}>
        <Card>
          <PageHeader
            className="mb-0"
            breadcrumbs={[{ label: d("header.org"), href: `/${lang}/courses` }, { label: d("header.courses"), href: `/${lang}/courses` }, { label: d("card.title") }]}
            title={d("card.title")}
            badge={<Badge tone="success" icon={<CircleCheck aria-hidden="true" />}>{d("badge.published")}</Badge>}
            description={d("header.description")}
            primaryAction={<Button leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{d("header.primary")}</Button>}
            secondaryActions={<><Button variant="secondary">{d("header.invite")}</Button><Button variant="secondary">{d("header.settings")}</Button></>}
          />
        </Card>
      </Section>

      <Section id="tabs" title={d("s.tabs")}>
        <Card>
          <Tabs id="demo-tabs" label={d("tabs.label")} items={tabItems} value={tab} onChange={setTab} />
          <TabPanel tabsId="demo-tabs" value={tab}>
            <p className="text-sm text-slate-700">{d("tabs.panel", { tab: tabItems.find((i) => i.id === tab)?.label ?? "" })}</p>
          </TabPanel>
          <p className="mb-2 mt-6 text-sm text-slate-600">{d("tabs.navNote")}</p>
          <TabsNav label={d("tabs.label")} items={tabItems.filter((i) => !i.disabled).map((i) => ({ href: `#tab-${i.id}`, label: i.label, active: i.id === "assessments", count: i.count }))} />
        </Card>
      </Section>

      <Section id="table" title={d("s.table")}>
        <div className="mb-3 max-w-xs">
          <Select label={d("table.viewState")} value={view} onChange={(e) => setView(e.target.value)}
            options={["data", "loading", "empty", "error"].map((v) => ({ value: v, label: d(`table.state${v[0].toUpperCase()}${v.slice(1)}`) }))} />
        </div>
        <Table<Student>
          caption={d("table.caption")}
          columns={columns}
          rows={view === "data" ? pageRows : []}
          rowKey={(s) => s.id}
          sort={sort}
          onSortChange={setSort}
          countText={view === "data" ? d("table.countText", { count: filtered.length }) : undefined}
          loading={view === "loading"}
          error={view === "error" ? <ErrorState title={d("table.errorTitle")} onRetry={() => setView("data")} /> : undefined}
          empty={<EmptyState variant="bordered" title={d("table.emptyTitle")} description={d("table.emptyBody")} action={<Button>{d("table.emptyAction")}</Button>} />}
          search={
            <FilterBar search={{ value: q, onChange: (v) => { setQ(v); setShown(5); } }}
              canReset={!!q || !!statusFilter} onReset={() => { setQ(""); setStatusFilter(""); }}>
              <Select label={d("table.status")} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} placeholder={d("table.allStatuses")}
                options={(["published", "inProgress", "late", "notPassed", "draft"] as Status[]).map((s) => ({ value: s, label: statusLabel(s) }))} />
            </FilterBar>
          }
          pagination={view === "data" ? {
            nextCursor: shown < filtered.length ? "next" : null,
            loading: moreLoading,
            shown: pageRows.length,
            total: filtered.length,
            onLoadMore: () => { setMoreLoading(true); setTimeout(() => { setShown((n) => n + 5); setMoreLoading(false); }, 600); },
          } : undefined}
        />
      </Section>

      <Section id="states" title={d("s.states")}>
        <div className="space-y-4">
          <EmptyState title={d("states.emptyTitle")} description={d("states.emptyBody")} action={<Button>{d("states.emptyAction")}</Button>} icon={<BookOpen />} />
          <ErrorState onRetry={() => toast.info(t("ui.retry"))} />
          <ErrorState variant="inline" title={d("states.inlineTitle")} message={d("states.inlineBody")} onRetry={() => undefined} retrying />
          <Card>
            <p className="mb-3 text-sm text-slate-600">{d("states.skeleton")}</p>
            <div className="mb-4 flex items-center gap-3"><Skeleton className="h-10 w-10 rounded-full" /><SkeletonText lines={2} className="flex-1" /></div>
            <LoadingState rows={2} />
          </Card>
        </div>
      </Section>

      <Section id="dialogs" title={d("s.dialogs")}>
        <Card>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <Button variant="secondary" onClick={() => setDialogOpen(true)}>{d("dialog.open")}</Button>
            <Button variant="danger" onClick={() => setConfirmOpen(true)}>{d("dialog.openConfirm")}</Button>
            <Button variant="secondary" onClick={() => setReasonOpen(true)}>{d("dialog.openReason")}</Button>
          </div>
        </Card>
        <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title={d("dialog.open")} description={d("dialog.description")}
          footer={<><Button variant="secondary" onClick={() => setDialogOpen(false)}>{t("ui.cancel")}</Button><Button onClick={() => { setDialogOpen(false); toast.success(d("toast.success")); }}>{t("ui.save")}</Button></>}>
          <Input label={d("dialog.newTitle")} defaultValue={d("card.title")} />
        </Dialog>
        <ConfirmDialog open={confirmOpen} tone="danger" title={d("dialog.confirmTitle")} object={d("card.title")} effect={d("dialog.confirmEffect")}
          confirmLabel={d("b.delete")} busy={confirmBusy} onCancel={() => setConfirmOpen(false)}
          onConfirm={() => { setConfirmBusy(true); setTimeout(() => { setConfirmBusy(false); setConfirmOpen(false); toast.success(d("dialog.done")); }, 900); }} />
        <ReasonDialog open={reasonOpen} tone="danger" title={d("dialog.reasonTitle")} object="Айжан Абдыкалыкова · aizhan.abdykalykova@school5.kg"
          effect={d("dialog.reasonEffect")} confirmLabel={d("dialog.reasonConfirm")} onCancel={() => setReasonOpen(false)}
          onConfirm={() => { setReasonOpen(false); toast.success(d("dialog.done")); }} />
      </Section>

      <Section id="toasts" title={d("s.toasts")}>
        <Card>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
            <Button variant="secondary" onClick={() => toast.success(d("toast.success"))}>{d("toast.showSuccess")}</Button>
            <Button variant="secondary" onClick={() => toast.error(d("toast.error"))}>{d("toast.showError")}</Button>
            <Button variant="secondary" onClick={() => toast.info(d("toast.info"))}>{d("toast.showInfo")}</Button>
          </div>
        </Card>
      </Section>

      <Section id="picker" title={d("s.picker")}>
        <Card className="pb-40 sm:pb-40">
          <div className="max-w-md">
            <UserPicker label={d("picker.label")} hint={d("picker.hint")} value={picked} onChange={setPicked} search={search} />
          </div>
        </Card>
      </Section>
    </main>
  );
}
