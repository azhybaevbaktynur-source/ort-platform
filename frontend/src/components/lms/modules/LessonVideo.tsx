"use client";

// LESSON_VIDEOS V4: the player of a platform-hosted lesson video (`video` item). The file sits in the private bucket;
// `GET …/items/{i}/play` gives a short-lived address (R2 presigned, or the dev stream with a token) that is used as the
// <video> source as is (no auth header needed). Not DRM: no download button, no context menu, no shareable link.
// - Address refresh: a timer fires 60 s before `expires_at`; while playing it fetches `/play` again and swaps the
//   source, resuming at the same time (paused players refresh on the next play). A playback error also refetches
//   (at most 3 times in a row, then an error card with "Повторить").
// - Position: remembered per item in localStorage (try/catch) and restored once the metadata is in.
// - View fact: `onWatched` once, when playback reaches 90 % of the duration (the lesson page sends `viewed`).
// - Captions: `captions_url` is an API route; it is fetched with the auth header and given to <track> as a blob URL.
import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getAuthHeader } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { getItemPlay } from "@/lib/lms/modules";
import type { VideoPlayOut } from "@/lib/lms/modulesTypes";
import { Button, Spinner, cn, focusRing } from "@/components/ui";
import { useModuleErrorText } from "./moduleUi";
import {
  VIDEO_RATES, isStale, positionToSave, reachedWatched, refreshDelay, resolveApiUrl, restorablePosition, storedRate,
} from "./videoPlayback";

const MAX_ERRORS = 3;
const POS_KEY = (itemId: string) => `ort_video_pos:${itemId}`;
const RATE_KEY = "ort_video_rate";
const toAbsolute = (url: string) => resolveApiUrl(url, window.location.origin, API_BASE_URL);

function readNumber(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key);
    const n = raw === null ? NaN : Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}
function writeValue(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // private mode or blocked storage: the player works without memory
  }
}

/** The captions file as a blob URL (the auth header goes only to the API origin). */
async function captionsBlobUrl(url: string, signal: AbortSignal): Promise<string | null> {
  const target = toAbsolute(url);
  const api = new URL(API_BASE_URL.replace(/\/?$/, "/"), window.location.origin);
  const headers = new URL(target).origin === api.origin ? await getAuthHeader() : {};
  const res = await fetch(target, { headers, cache: "no-store", signal });
  if (!res.ok) return null;
  const text = await res.text();
  return URL.createObjectURL(new Blob([text], { type: "text/vtt" }));
}

export function LessonVideo({ courseId, moduleId, itemId, title, durationS, onWatched, remember = true }: {
  courseId: string;
  moduleId: string;
  itemId: string;
  title: string;
  /** the server's duration from the outline (until the metadata says better) */
  durationS?: number | null;
  /** once, at 90 % of the duration */
  onWatched?: () => void;
  /** keep the position in localStorage (off in the staff preview) */
  remember?: boolean;
}) {
  const { lang, t } = useTranslation();
  const errorText = useModuleErrorText();
  const rateId = useId();
  const video = useRef<HTMLVideoElement>(null);
  const [play, setPlay] = useState<VideoPlayOut | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  // a new element per address: the same URL again (a real media error) still reloads, and counts towards MAX_ERRORS
  const [gen, setGen] = useState(0);
  const [captions, setCaptions] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [failed, setFailed] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [rate, setRate] = useState<number>(1);

  // the time to seek to (and whether to play) once the next source's metadata is in
  const resume = useRef<{ time: number; play: boolean } | null>(null);
  const errors = useRef(0);
  const fetching = useRef(false);
  const watched = useRef(false);
  const lastSaved = useRef(0);
  // the last known time and duration (the element is gone on unmount and after a failure)
  const lastTime = useRef(0);
  const lastDuration = useRef(0);
  const live = useRef(true);
  const watchedCb = useRef(onWatched);
  watchedCb.current = onWatched;

  const fetchPlay = useCallback(async (next: { time: number; play: boolean } | null) => {
    if (fetching.current) return;
    fetching.current = true;
    setError(null);
    try {
      const out = await getItemPlay(courseId, moduleId, itemId);
      if (!live.current) return;
      if (next) resume.current = next;
      setPlay(out);
      setSrc(toAbsolute(out.url));
      setGen((g) => g + 1);
    } catch (e) {
      if (!live.current) return;
      setError(e);
      setFailed(true);
      setWaiting(false);
    } finally {
      fetching.current = false;
    }
  }, [courseId, moduleId, itemId]);

  // first address; the remembered position and rate are restored on the metadata
  useEffect(() => {
    live.current = true;
    watched.current = false;
    errors.current = 0;
    lastTime.current = 0;
    const saved = remember ? readNumber(POS_KEY(itemId)) : null;
    resume.current = saved !== null ? { time: saved, play: false } : null;
    const r = storedRate(readNumber(RATE_KEY));
    if (r !== null) setRate(r);
    void fetchPlay(null);
    return () => { live.current = false; };
  }, [itemId, remember, fetchPlay]);

  // refresh 60 s before expiry while playing; a paused player refreshes on its next "play"
  useEffect(() => {
    if (!play) return;
    const delay = refreshDelay(play.expires_at, Date.now());
    if (delay === null) return;
    const timer = window.setTimeout(() => {
      const v = video.current;
      if (v && !v.paused && !v.ended) void fetchPlay({ time: v.currentTime, play: true });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [play, fetchPlay]);

  // captions once per address set (an API route: fetched with the auth header, handed to <track> as a blob)
  const captionsUrl = play?.captions_url ?? null;
  useEffect(() => {
    if (!captionsUrl) return;
    const ctrl = new AbortController();
    let made: string | null = null;
    captionsBlobUrl(captionsUrl, ctrl.signal)
      .then((u) => { made = u; if (u) setCaptions(u); })
      .catch(() => undefined); // the video plays without captions
    return () => {
      ctrl.abort();
      if (made) URL.revokeObjectURL(made);
      setCaptions(null);
    };
  }, [captionsUrl]);

  useEffect(() => { if (video.current) video.current.playbackRate = rate; }, [rate, src]);

  const savePosition = useCallback((force = false) => {
    if (!remember || lastTime.current <= 0) return;
    const now = Date.now();
    if (!force && now - lastSaved.current < 5_000) return;
    lastSaved.current = now;
    // near the end the next visit starts from the beginning
    const pos = positionToSave(lastTime.current, lastDuration.current);
    writeValue(POS_KEY(itemId), pos === null ? null : String(pos));
  }, [remember, itemId]);

  useEffect(() => {
    const onHide = () => savePosition(true);
    window.addEventListener("pagehide", onHide);
    return () => { window.removeEventListener("pagehide", onHide); savePosition(true); };
  }, [savePosition]);

  const onLoadedMetadata = () => {
    const v = video.current;
    if (!v) return;
    v.playbackRate = rate;
    setWaiting(false);
    const r = resume.current;
    resume.current = null;
    if (!r) return;
    const at = restorablePosition(r.time, v.duration);
    if (at !== null) v.currentTime = at;
    if (r.play) v.play().catch(() => undefined);
  };

  const onTimeUpdate = () => {
    const v = video.current;
    if (!v) return;
    const duration = Number.isFinite(v.duration) && v.duration > 0 ? v.duration : (play?.duration_s || durationS || 0);
    lastTime.current = v.currentTime;
    lastDuration.current = duration;
    savePosition();
    if (!watched.current && !v.paused && reachedWatched(v.currentTime, duration)) {
      watched.current = true;
      watchedCb.current?.();
    }
  };

  const onPlay = () => {
    const v = video.current;
    if (v && play && isStale(play.expires_at, Date.now())) void fetchPlay({ time: v.currentTime, play: true });
  };

  const onError = () => {
    const v = video.current;
    errors.current += 1;
    if (errors.current > MAX_ERRORS) { setFailed(true); setWaiting(false); return; }
    // an expired or broken address: a fresh one, at the same time
    void fetchPlay({ time: v?.currentTime || lastTime.current, play: !!v && !v.paused });
  };

  const retry = () => {
    errors.current = 0;
    setFailed(false);
    setSrc(null);
    void fetchPlay({ time: lastTime.current, play: false });
  };

  const fmtRate = (r: number) => `${new Intl.NumberFormat(lang).format(r)}×`;
  const code = (error as { code?: string } | null)?.code;
  // a spinner until the first address is in and while the element waits for data (never over an error)
  const busy = !failed && (!src || waiting);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="relative aspect-video w-full overflow-hidden rounded-card bg-navy-800">
        {src && !failed && (
          <video key={gen} ref={video} src={src} aria-label={title}
            className="absolute inset-0 h-full w-full bg-black object-contain"
            controls preload="metadata" playsInline controlsList="nodownload"
            onContextMenu={(e) => e.preventDefault()}
            onLoadedMetadata={onLoadedMetadata} onTimeUpdate={onTimeUpdate} onPlay={onPlay}
            onPause={() => savePosition(true)} onEnded={() => savePosition(true)} onError={onError}
            onWaiting={() => setWaiting(true)} onCanPlay={() => setWaiting(false)}
            onPlaying={() => { setWaiting(false); errors.current = 0; }} onLoadedData={() => setWaiting(false)}>
            {captions && <track kind="subtitles" src={captions} srcLang={lang} label={t("modules.lesson.video.captions")} />}
          </video>
        )}
        {busy && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <Spinner className="h-8 w-8 text-white" />
          </div>
        )}
        {busy && <span role="status" className="sr-only">{t("modules.lesson.video.loading")}</span>}
        {failed && (
          <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center text-white">
            <AlertTriangle aria-hidden="true" className="h-8 w-8 text-white/80" />
            <p className="max-w-sm text-sm leading-5">
              {code === "item_locked" ? t("modules.errors.item_locked") : error ? errorText(error) : t("modules.lesson.video.error")}
            </p>
            {code !== "item_locked" && (
              <Button variant="secondary" size="sm" onClick={retry}>{t("lms.common.retry")}</Button>
            )}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <label htmlFor={rateId} className="text-sm font-medium text-slate-700">{t("modules.lesson.video.speed")}</label>
        <select id={rateId} value={String(rate)} disabled={failed}
          onChange={(e) => { const r = Number(e.target.value); setRate(r); writeValue(RATE_KEY, String(r)); }}
          className={cn("min-h-11 rounded-control border border-slate-300 bg-white px-3 text-sm text-slate-900 disabled:opacity-60", focusRing)}>
          {VIDEO_RATES.map((r) => <option key={r} value={String(r)}>{fmtRate(r)}</option>)}
        </select>
        {captions && <span className="text-sm leading-5 text-slate-600">{t("modules.lesson.video.captionsHint")}</span>}
      </div>
    </div>
  );
}
