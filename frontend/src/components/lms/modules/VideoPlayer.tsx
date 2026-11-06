"use client";

// Student UI U7 (STUDENT_UI_DESIGN §3.5, §4.4): the click-to-load player. Before the tap it is our own navy card with a
// play button: no request goes to YouTube or Vimeo. The tap inserts the provider's player (no-cookie YouTube, Vimeo
// with `dnt`), built from the validated id only, in a sandboxed iframe (CSP `frame-src` allows exactly these origins).
import React, { useEffect, useId, useRef, useState } from "react";
import { Play } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import type { VideoOut } from "@/lib/lms/modulesTypes";
import { cn, focusRing } from "@/components/ui";
import { videoEmbedUrl } from "./lessons";

/** F5b (COURSE_LESSONS_DESIGN 4): `onPlay` runs on the tap; the lesson page records the view there, not on open. */
export function VideoPlayer({ video, title, onPlay }: { video: VideoOut; title: string; onPlay?: () => void }) {
  const { t } = useTranslation();
  const [on, setOn] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const hintId = useId();
  const src = videoEmbedUrl(video);
  // the button disappears on tap: keyboard focus moves to the player instead of the page body
  useEffect(() => { if (on) frame.current?.focus(); }, [on]);
  if (!src) return null;
  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-card bg-navy-800">
      {on ? (
        <iframe ref={frame} src={src} title={title} className="absolute inset-0 h-full w-full border-0"
          allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen
          referrerPolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-presentation" />
      ) : (
        <button type="button" onClick={() => { setOn(true); onPlay?.(); }} aria-label={t("modules.lesson.play", { title })} aria-describedby={hintId}
          className={cn("group absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center text-white", focusRing, "focus-visible:ring-inset focus-visible:ring-offset-0")}>
          <span aria-hidden="true" className="flex h-16 w-16 items-center justify-center rounded-full bg-white text-navy-800 shadow-lg transition-transform group-hover:scale-105 sm:h-20 sm:w-20">
            <Play className="ml-1 h-8 w-8 fill-current sm:h-9 sm:w-9" />
          </span>
          <span id={hintId} className="max-w-sm text-sm leading-5 text-white/80">
            {t(video.provider === "vimeo" ? "modules.lesson.playHintVimeo" : "modules.lesson.playHintYoutube")}
          </span>
        </button>
      )}
    </div>
  );
}
