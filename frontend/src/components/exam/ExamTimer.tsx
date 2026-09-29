"use client";

import React, { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";

interface ExamTimerProps {
  initialSeconds?: number | null;
  onTimeExpired: () => void;
}

export const ExamTimer: React.FC<ExamTimerProps> = ({ initialSeconds, onTimeExpired }) => {
  const { lang } = useTranslation();
  const isUnlimited = initialSeconds == null || initialSeconds <= 0;
  const [secondsLeft, setSecondsLeft] = useState<number>(initialSeconds || 0);

  useEffect(() => {
    if (isUnlimited) return;

    if (secondsLeft <= 0) {
      onTimeExpired();
      return;
    }

    const interval = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          onTimeExpired();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [secondsLeft, onTimeExpired, isUnlimited]);

  if (isUnlimited) {
    return (
      <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl border border-slate-300 bg-slate-100 font-mono font-bold text-sm tracking-wider text-slate-700 shadow-xs">
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
      className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl border font-mono font-bold text-sm tracking-wider shadow-xs transition-colors ${
        isUrgent
          ? "bg-rose-50 border-rose-300 text-rose-700 animate-pulse"
          : "bg-slate-100 border-slate-300 text-slate-800"
      }`}
    >
      <Clock className={`w-4 h-4 ${isUrgent ? "text-rose-600" : "text-slate-600"}`} />
      <span>
        {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
      </span>
    </div>
  );
};
