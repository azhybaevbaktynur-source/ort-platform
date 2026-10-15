"use client";

import React, { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";

interface ExamTimerProps {
  initialSeconds?: number | null;
  onTimeExpired: () => void;
  onTick?: (secondsLeft: number) => void;
}

export const ExamTimer: React.FC<ExamTimerProps> = ({ initialSeconds, onTimeExpired, onTick }) => {
  const { lang } = useTranslation();
  const isUnlimited = initialSeconds == null || initialSeconds <= 0;
  const [secondsLeft, setSecondsLeft] = useState<number>(initialSeconds || 0);

  const onTimeExpiredRef = React.useRef(onTimeExpired);
  const onTickRef = React.useRef(onTick);
  const hasExpiredRef = React.useRef(false);

  useEffect(() => {
    onTimeExpiredRef.current = onTimeExpired;
    onTickRef.current = onTick;
  });

  useEffect(() => {
    setSecondsLeft(initialSeconds || 0);
    hasExpiredRef.current = false;
  }, [initialSeconds]);

  useEffect(() => {
    if (isUnlimited) return;

    if (initialSeconds != null && initialSeconds <= 0 && !hasExpiredRef.current) {
      hasExpiredRef.current = true;
      const timer = setTimeout(() => {
        onTimeExpiredRef.current?.();
      }, 0);
      return () => clearTimeout(timer);
    }

    const interval = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          if (!hasExpiredRef.current) {
            hasExpiredRef.current = true;
            setTimeout(() => {
              onTimeExpiredRef.current?.();
            }, 0);
          }
          return 0;
        }
        const next = prev - 1;
        onTickRef.current?.(next);
        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isUnlimited, initialSeconds]);

  if (isUnlimited) {
    return (
      <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-slate-200 bg-slate-50 font-mono font-bold text-sm tracking-wider text-slate-700 shadow-xs">
        <Clock className="w-4 h-4 text-slate-500" />
        <span>{lang === "ky" ? "Чектөөсүз" : "Без лимита"}</span>
      </div>
    );
  }

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const isUrgent = secondsLeft < 300; // Under 5 minutes

  return (
    <div
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-full border font-mono font-bold text-sm tracking-wider shadow-xs transition-colors ${
        isUrgent
          ? "bg-rose-50 border-rose-300 text-rose-700 animate-pulse shadow-rose-100"
          : "bg-slate-50 border-slate-200 text-slate-800"
      }`}
    >
      <Clock className={`w-4 h-4 ${isUrgent ? "text-rose-600" : "text-indigo-600"}`} />
      <span>
        {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
      </span>
    </div>
  );
};
