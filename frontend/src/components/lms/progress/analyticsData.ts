/*
 * Student UI U6 (STUDENT_UI_DESIGN §3.3): pure helpers for the analytics page. No React, no requests.
 */
import type { CSSProperties } from "react";
import type { ActivityDay, ActivityDays, TopicStat } from "@/lib/lms/progress";

export const PERIODS: ActivityDays[] = [7, 30, 90, 365];

/** Section keys shown in the "Математика" card; the language card takes LANGUAGE_SECTIONS, anything else "other". */
export const MATH_SECTIONS = new Set(["math_1", "math_2", "advanced_math"]);
export const LANGUAGE_SECTIONS = new Set(["analogies", "reading", "grammar", "native_language", "english"]);

/**
 * Stack colour of a section (study time chart). Fixed by entity, never by rank; the order was checked for colour-blind
 * separation of neighbours (dataviz validator): math_1, math_2, analogies, reading, grammar, other.
 */
export const SECTION_ORDER = ["math_1", "math_2", "analogies", "reading", "grammar"] as const;
export const SECTION_FILL: Record<string, string> = {
  math_1: "rgb(var(--brand-800))", // brand ramp (800 .. 200), darkest first; the legend names the sections
  math_2: "rgb(var(--brand-600))",
  analogies: "rgb(var(--brand-400))",
  reading: "rgb(var(--brand-300))",
  grammar: "rgb(var(--brand-200))",
};
export const OTHER_FILL = "#94a3b8"; // slate-400

/** Correct answers: brand blue; wrong ones: neutral grey, hatched so colour is never the only difference (4.1). */
export const CORRECT_FILL = "rgb(var(--brand-600))";
export const WRONG_STYLE: CSSProperties = {
  backgroundImage: "repeating-linear-gradient(135deg, #64748b 0 3px, #cbd5e1 3px 5px)",
};

/** One bar of a time chart: a day, or a week (Monday first) for the one-year period. */
export interface Bucket {
  /** First day, `YYYY-MM-DD`. */
  start: string;
  /** Last day, `YYYY-MM-DD` (the same as `start` for a day). */
  end: string;
  answered: number;
  correct: number;
  wrong: number;
  seconds: number;
  /** section key -> seconds ("" for answers without a section). */
  sections: Record<string, number>;
}

const DAY_MS = 86_400_000;
export const dayMs = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, (m || 1) - 1, d || 1);
};
const isoOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);

function toBucket(d: ActivityDay): Bucket {
  const sections: Record<string, number> = {};
  let known = 0;
  for (const [k, v] of Object.entries(d.by_section ?? {})) {
    sections[k] = (sections[k] ?? 0) + v;
    known += v;
  }
  const rest = d.study_seconds - known;
  if (rest > 0) sections[""] = (sections[""] ?? 0) + rest;
  return { start: d.date, end: d.date, answered: d.answered, correct: d.correct, wrong: d.wrong, seconds: d.study_seconds, sections };
}

/** Days as they come, or weeks (Monday to Sunday) when the period is a year (365 bars would be too thin). */
export function bucketize(days: ActivityDay[], period: ActivityDays): { unit: "day" | "week"; buckets: Bucket[] } {
  const daily = days.map(toBucket);
  if (period !== 365) return { unit: "day", buckets: daily };
  const weeks = new Map<string, Bucket>();
  for (const b of daily) {
    const ms = dayMs(b.start);
    const monday = isoOf(ms - ((new Date(ms).getUTCDay() + 6) % 7) * DAY_MS);
    const w = weeks.get(monday);
    if (!w) {
      weeks.set(monday, { ...b, start: monday, sections: { ...b.sections } });
      continue;
    }
    w.end = b.end;
    w.answered += b.answered;
    w.correct += b.correct;
    w.wrong += b.wrong;
    w.seconds += b.seconds;
    for (const [k, v] of Object.entries(b.sections)) w.sections[k] = (w.sections[k] ?? 0) + v;
  }
  return { unit: "week", buckets: [...weeks.values()] };
}

/** A round axis maximum (1, 2, 5, 10, 20, 50 ...) at or above `v`, at least `floor`. */
export function niceMax(v: number, floor = 1): number {
  const x = Math.max(v, floor);
  const p = 10 ** Math.floor(Math.log10(x));
  for (const m of [1, 2, 5, 10]) if (m * p >= x) return m * p;
  return 10 * p;
}

/** An even axis maximum for counts (2, 4, 6, 10, 20, 40 ...), so the middle grid line is a whole number. */
export function niceCount(v: number): number {
  const x = Math.max(v, 2);
  const p = 10 ** Math.floor(Math.log10(x));
  for (const m of [1, 2, 4, 6, 10]) if (m * p >= x && (m * p) % 2 === 0) return m * p;
  return 20 * p;
}

/** Active days (all time) before the activity calendar appears. */
export const HEATMAP_MIN_DAYS = 7;

/** A named topic (the server's no-topic bucket, `topic` null, only keeps the sums equal and is never listed). */
export type NamedTopic = TopicStat & { topic: string };
export const namedTopics = (topics: TopicStat[]): NamedTopic[] => topics.filter((t): t is NamedTopic => t.topic !== null);

/** STUDENT_UI_FIX_PLAN 4.3: a topic shows a percent and a band only when the server rates it (5 graded answers). */
export const isGraded = (t: TopicStat) => t.rated;

/**
 * The five weakest topics: lowest accuracy first, more answers first on a tie, rated topics only. Null until the server
 * says `weak_topics_ready` (3 rated topics; the card is not shown); an empty list: enough data and nothing weak.
 */
export function weakestTopics(topics: NamedTopic[], ready: boolean, n = 5): NamedTopic[] | null {
  if (!ready) return null;
  // a topic in the green band (85 % and above) is never "weak"
  return topics.filter((t) => t.rated && toPercent(t.accuracy) < 85)
    .sort((a, b) => a.accuracy - b.accuracy || b.total - a.total || a.topic.localeCompare(b.topic))
    .slice(0, n);
}

export type TopicGroup = "math" | "language" | "other";
export function topicGroup(section: string | null): TopicGroup {
  if (section && MATH_SECTIONS.has(section)) return "math";
  if (section && LANGUAGE_SECTIONS.has(section)) return "language";
  return "other";
}

/** "05" for the weak-topic list. */
export const twoDigits = (n: number) => String(n).padStart(2, "0");

/** Percent 0-100 from a 0..1 share. */
export const toPercent = (share: number) => Math.round(Math.max(0, Math.min(1, share || 0)) * 100);
