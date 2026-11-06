import React from "react";
import { cn } from "@/components/ui/utils";

/*
 * F5b (COURSE_LESSONS_DESIGN L10, 8): the course cover. Until problem 7 stores a real cover (`cover_url`, added
 * there as a prop), every course gets this default: the student palette's teal-to-sky gradient (the sidebar's
 * navy-800 → #13698f, then brand-500), soft rings and the course's mark (a short first word such as "ОРТ", else its
 * first letter). Decorative only: the course title is always written next to it.
 */

/** "ОРТ (на русском)" → "ОРТ"; "Математика 9" → "М". */
export function courseMark(title: string): string {
  const first = title.trim().split(/[\s(«"'.,:;-]+/).find(Boolean) ?? "";
  if (!first) return "";
  return first.length <= 4 ? first.toUpperCase() : first[0].toUpperCase();
}

export function CourseCover({ title, coverUrl, className }: { title: string; coverUrl?: string | null; className?: string }) {
  // F7b: the uploaded cover (a 16:9 WebP); a wider banner shows its middle band
  if (coverUrl) {
    return (
      <div aria-hidden="true" className={cn("relative overflow-hidden bg-slate-100", className)}>
        {/* eslint-disable-next-line @next/next/no-img-element -- a public R2/media URL, sized by the box */}
        <img src={coverUrl} alt="" decoding="async" className="absolute inset-0 h-full w-full object-cover" />
      </div>
    );
  }
  const mark = courseMark(title);
  return (
    <div aria-hidden="true"
      className={cn("relative isolate overflow-hidden bg-gradient-to-br from-navy-800 via-[#13698f] to-brand-500", className)}>
      {/* a light dot grid and two soft rings: texture without a second hue */}
      <div className="absolute inset-0 opacity-[0.18]"
        style={{ backgroundImage: "radial-gradient(rgba(255,255,255,0.9) 1px, transparent 1.5px)", backgroundSize: "18px 18px" }} />
      <div className="absolute -right-16 -top-24 h-72 w-72 rounded-full border-[28px] border-white/10" />
      <div className="absolute -bottom-28 left-[38%] h-64 w-64 rounded-full bg-white/[0.06]" />
      {mark && (
        <span className="absolute bottom-3 right-5 select-none text-[56px] font-extrabold leading-none tracking-tight text-white/25 sm:bottom-4 sm:right-8 sm:text-[80px]">
          {mark}
        </span>
      )}
    </div>
  );
}
