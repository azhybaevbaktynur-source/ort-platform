"use client";

// Phase 7a S5: accommodations on the People tab (teacher only; PHASE_7A_DESIGN 4.4, 5): every student with a summary
// badge ("+25 % time, +1 attempt") and a "Accommodations" button that opens the dialog. Roster-paginated.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Accessibility } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { accommodationParts, listAccommodations, type AccommodationOut, type AccommodationRowOut } from "@/lib/lms/accommodations";
import { useTemplateUi } from "@/lib/lms/templates";
import { Badge, Button, Card, SearchInput, Table, type TableColumn } from "@/components/ui";
import { AssignmentError } from "@/components/lms/assignments/assignmentUi";
import { AccommodationDialog } from "./AccommodationDialog";

export function useAccommodationText() {
  const { t } = useTranslation();
  return (a: AccommodationOut | null | undefined): string => {
    const p = accommodationParts(a);
    if (!p) return "";
    const parts: string[] = [];
    if (p.percent) parts.push(t("accommodations.badge.percent", { n: p.percent }));
    if (p.minutes) parts.push(t("accommodations.badge.minutes", { n: p.minutes }));
    if (p.attempts) parts.push(t("accommodations.badge.attempts", { n: p.attempts }));
    return parts.join(", ");
  };
}

export function AccommodationsSection({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const ui = useTemplateUi();
  const text = useAccommodationText();
  const [rows, setRows] = useState<AccommodationRowOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<AccommodationRowOut | null>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listAccommodations(courseId, { cursor: next, limit: 50 });
      setRows((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  const q = query.trim().toLowerCase();
  const visible = useMemo(() => (q ? rows.filter((r) => `${r.student_name ?? ""} ${r.email ?? ""}`.toLowerCase().includes(q)) : rows), [rows, q]);
  const withAny = rows.filter((r) => !!accommodationParts(r.accommodation)).length;

  const columns: TableColumn<AccommodationRowOut>[] = [
    { key: "student", header: t("gradebook.student"), primary: true, cell: (r) => <span className="break-words">{r.student_name || r.email || "—"}</span> },
    {
      key: "acc", header: t("accommodations.section.colAccommodations"), mobilePriority: 0,
      cell: (r) => {
        const s = text(r.accommodation);
        return s ? <Badge tone="info" icon={<Accessibility aria-hidden="true" />}>{s}</Badge> : <span className="text-slate-600">{t("accommodations.section.none")}</span>;
      },
    },
    {
      key: "act", header: "", actions: true, align: "right",
      cell: (r) => (
        <Button variant="secondary" size="sm" onClick={() => setEditing(r)}>
          {t("accommodations.section.open")}<span className="sr-only">: {r.student_name || r.email}</span>
        </Button>
      ),
    },
  ];

  return (
    <Card title={t("accommodations.section.title")} description={t("accommodations.section.subtitle")}>
      <Table<AccommodationRowOut>
        caption={t("accommodations.section.title")}
        rows={visible}
        rowKey={(r) => r.enrollment_id}
        columns={columns}
        loading={loading}
        countText={!loading && rows.length > 0 ? t("accommodations.section.count", { n: withAny, total: rows.length }) : undefined}
        search={rows.length > 8 ? <SearchInput value={query} onChange={setQuery} label={t("accommodations.section.search")} /> : undefined}
        error={error ? <AssignmentError error={error} onRetry={() => void load()} /> : undefined}
        empty={<p className="rounded-xl border border-dashed border-slate-300 p-4 text-center text-sm text-slate-600">{t("accommodations.section.empty")}</p>}
        pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }}
      />
      <AccommodationDialog open={!!editing} courseId={courseId} row={editing} ortCourse={ui.key === "ort"}
        onClose={() => setEditing(null)}
        onSaved={(id, acc) => { setRows((rs) => rs.map((r) => (r.enrollment_id === id ? { ...r, accommodation: acc } : r))); setEditing(null); }} />
    </Card>
  );
}
