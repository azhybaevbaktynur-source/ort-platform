"use client";

// F7c: the cover of a course: cards (16:9), the overview banner and the settings preview. The teacher's picture (`cover_url`, already 1280 x 720 WebP) or a generated
// default: a soft gradient of the brand tints, a pale shape and one quiet mark (a book; a graduation cap for platform courses), the tint picked from the course id, so a
// course looks the same everywhere. Never a dark or saturated colour (STUDENT_UI_FIX_PLAN 4.1, 7.1).
import React from "react";
import { BookOpen, GraduationCap } from "lucide-react";
import { cn } from "@/components/ui";

const TINTS = [
  "from-brand-100 to-brand-50",
  "from-brand-200/70 to-brand-50",
  "from-brand-50 to-brand-100",
  "from-brand-100 via-brand-50 to-brand-100",
];

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

export function CourseCardCover({ courseId, coverUrl, platform = false, card = false, className }: {
  courseId: string;
  coverUrl?: string | null;
  /** a platform (exam preparation) course gets the graduation mark */
  platform?: boolean;
  /** the course card: a fixed 150 px strip instead of 16:9 (banner and settings keep 16:9) */
  card?: boolean;
  className?: string;
}) {
  const h = hash(courseId);
  const Icon = platform ? GraduationCap : BookOpen; // one neutral mark; platform (exam preparation) courses their own
  return (
    <div className={cn("relative w-full overflow-hidden bg-brand-50", card ? "h-[150px]" : "aspect-video", className)}>
      {coverUrl
        // eslint-disable-next-line @next/next/no-img-element
        ? <img src={coverUrl} alt="" loading="lazy" decoding="async" draggable={false} className="h-full w-full object-cover" />
        : (
          <div aria-hidden="true" className={cn("absolute inset-0 bg-gradient-to-br", TINTS[(h >>> 3) % TINTS.length])}>
            <span className="absolute -right-8 -top-10 h-36 w-36 rounded-full bg-navy-800/10" />
            <span className="absolute -bottom-12 left-6 h-28 w-28 rounded-full bg-white/50" />
            <Icon strokeWidth={1.5} className="absolute bottom-3 right-4 h-12 w-12 text-brand-700/60" />
          </div>
        )}
    </div>
  );
}
