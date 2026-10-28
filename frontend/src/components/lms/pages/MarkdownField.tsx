"use client";

// Phase 8a S4b: Markdown textarea with a toolbar (bold, italic, heading, list, link, image, formula) and a live preview
// rendered by the server (`POST pages/preview`, debounced 600 ms; the response is sanitized HTML, never client-rendered
// Markdown). Shared by the page editor and the announcement composer.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bold, Heading2, Image as ImageIcon, Italic, Link2, List, Sigma } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { previewMarkdown } from "@/lib/lms/pages";
import { ImagePicker } from "@/components/lms/content/ImagePicker";
import { Button, Dialog, IconButton, Input, Spinner, Textarea } from "@/components/ui";
import { ContentError } from "./ApiError";
import { SafeHtml } from "./SafeHtml";

type Wrap = { before: string; after: string; sample: string };

export function MarkdownField({
  courseId, label, value, onChange, max, disabled, rows = 14,
}: {
  courseId: string; label: string; value: string; onChange: (v: string) => void; max: number; disabled?: boolean; rows?: number;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [html, setHtml] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<"link" | "image" | null>(null);
  const [linkUrl, setLinkUrl] = useState("https://");
  const [linkText, setLinkText] = useState("");
  const [alt, setAlt] = useState("");
  const sel = useRef({ start: 0, end: 0 });

  // Debounced server preview
  useEffect(() => {
    if (!value.trim()) { setHtml(""); setPreviewError(null); return; }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await previewMarkdown(courseId, value, ctrl.signal);
        setHtml(r.body_html);
        setPreviewError(null);
      } catch (e) {
        if (!(e instanceof DOMException && e.name === "AbortError")) setPreviewError(e);
      } finally {
        if (!ctrl.signal.aborted) setBusy(false);
      }
    }, 600);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [courseId, value]);

  const insert = useCallback((text: string, selectFrom?: number, selectLen?: number) => {
    const { start, end } = sel.current;
    const next = value.slice(0, start) + text + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      const from = start + (selectFrom ?? text.length);
      el.setSelectionRange(from, from + (selectLen ?? 0));
    });
  }, [value, onChange]);

  const remember = () => {
    const el = ref.current;
    if (el) sel.current = { start: el.selectionStart, end: el.selectionEnd };
  };

  const wrap = ({ before, after, sample }: Wrap) => {
    remember();
    const { start, end } = sel.current;
    const chosen = value.slice(start, end) || sample;
    insert(before + chosen + after, before.length, chosen.length);
  };
  const linePrefix = (prefix: string) => {
    remember();
    const { start, end } = sel.current;
    const chosen = value.slice(start, end) || t("pages.toolbar.sample");
    const text = chosen.split("\n").map((l) => prefix + l).join("\n");
    const lead = start > 0 && value[start - 1] !== "\n" ? "\n" : "";
    insert(lead + text, lead.length + text.length);
  };

  const openDialog = (kind: "link" | "image") => {
    remember();
    const { start, end } = sel.current;
    setLinkText(value.slice(start, end));
    setAlt("");
    setLinkUrl("https://");
    setDialog(kind);
  };

  const tools: { id: string; label: string; icon: React.ReactNode; run: () => void }[] = [
    { id: "bold", label: t("pages.toolbar.bold"), icon: <Bold className="h-4 w-4" />, run: () => wrap({ before: "**", after: "**", sample: t("pages.toolbar.sample") }) },
    { id: "italic", label: t("pages.toolbar.italic"), icon: <Italic className="h-4 w-4" />, run: () => wrap({ before: "*", after: "*", sample: t("pages.toolbar.sample") }) },
    { id: "heading", label: t("pages.toolbar.heading"), icon: <Heading2 className="h-4 w-4" />, run: () => linePrefix("## ") },
    { id: "list", label: t("pages.toolbar.list"), icon: <List className="h-4 w-4" />, run: () => linePrefix("- ") },
    { id: "link", label: t("pages.toolbar.link"), icon: <Link2 className="h-4 w-4" />, run: () => openDialog("link") },
    { id: "image", label: t("pages.toolbar.image"), icon: <ImageIcon className="h-4 w-4" />, run: () => openDialog("image") },
    { id: "math", label: t("pages.toolbar.math"), icon: <Sigma className="h-4 w-4" />, run: () => wrap({ before: "$", after: "$", sample: "x^2" }) },
  ];

  const applyLink = () => {
    const url = linkUrl.trim();
    if (!url) return;
    insert(`[${linkText.trim() || url}](${url})`);
    setDialog(null);
  };

  return (
    <div>
      <p className="text-sm font-medium text-slate-800">{label}</p>
      <div role="toolbar" aria-label={t("pages.toolbar.label")} className="mt-1 flex flex-wrap gap-1 rounded-t-xl border border-b-0 border-slate-300 bg-slate-50 p-1">
        {tools.map((x) => (
          <IconButton key={x.id} aria-label={x.label} icon={x.icon} variant="ghost" disabled={disabled} onMouseDown={(ev) => ev.preventDefault()} onClick={x.run} />
        ))}
      </div>
      <Textarea
        ref={ref}
        label={<span className="sr-only">{label}</span>}
        rows={rows}
        value={value}
        disabled={disabled}
        onChange={(ev) => onChange(ev.target.value)}
        onBlur={remember}
        className="!mt-0 rounded-t-none font-mono text-sm"
        hint={t("pages.toolbar.counter", { count: value.length, max })}
        error={value.length > max ? t("pages.errors.payload_too_large") : undefined}
      />
      <div className="mt-4">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-800">
          {t("pages.preview.title")} {busy && <Spinner className="h-4 w-4" />}
        </p>
        <div className="mt-1 min-h-24 rounded-xl border border-slate-200 bg-white p-4" aria-live="polite">
          {previewError ? <ContentError error={previewError} /> : html ? <SafeHtml html={html} /> : (
            <p className="text-sm text-slate-600">{value.trim() ? t("pages.preview.loading") : t("pages.preview.empty")}</p>
          )}
        </div>
      </div>

      <Dialog
        open={dialog === "link"}
        onClose={() => setDialog(null)}
        title={t("pages.toolbar.linkTitle")}
        footer={<>
          <Button variant="secondary" onClick={() => setDialog(null)}>{t("common.cancel")}</Button>
          <Button onClick={applyLink} disabled={!linkUrl.trim()}>{t("pages.toolbar.insert")}</Button>
        </>}
      >
        <div className="space-y-3">
          <Input label={t("pages.toolbar.linkText")} value={linkText} onChange={(ev) => setLinkText(ev.target.value)} />
          <Input label={t("pages.toolbar.linkUrl")} type="url" inputMode="url" value={linkUrl} onChange={(ev) => setLinkUrl(ev.target.value)} hint={t("pages.toolbar.linkHint")} />
        </div>
      </Dialog>

      <Dialog open={dialog === "image"} onClose={() => setDialog(null)} title={t("pages.toolbar.imageTitle")} size="lg"
        footer={<Button variant="secondary" onClick={() => setDialog(null)}>{t("common.cancel")}</Button>}>
        <div className="space-y-3">
          <Input label={t("pages.toolbar.imageAlt")} value={alt} onChange={(ev) => setAlt(ev.target.value)} hint={t("pages.toolbar.imageAltHint")} />
          <ImagePicker
            courseId={courseId}
            value={null}
            onChange={(img) => {
              if (!img) return;
              insert(`![${alt.trim()}](${img.url})`);
              setDialog(null);
            }}
          />
        </div>
      </Dialog>
    </div>
  );
}
