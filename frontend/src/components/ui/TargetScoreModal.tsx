"use client";

import React, { useState, useEffect } from "react";
import { Target, X, Check, Award, GraduationCap, BookOpen, AlertCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";

interface TargetScoreModalProps {
  isOpen: boolean;
  initialScore: number;
  onClose: () => void;
  onSave: (newScore: number) => Promise<void>;
}

export const TargetScoreModal: React.FC<TargetScoreModalProps> = ({
  isOpen,
  initialScore,
  onClose,
  onSave,
}) => {
  const { lang, t } = useTranslation();
  const [score, setScore] = useState<number>(initialScore || 200);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setScore(initialScore || 200);
      setError(null);
    }
  }, [isOpen, initialScore]);

  if (!isOpen) return null;

  const handleQuickSelect = (val: number) => {
    setScore(val);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isNaN(score) || score < 60 || score > 245) {
      setError(
        lang === "ky"
          ? "Балл 60 менен 245 ортосунда болушу керек"
          : "Балл должен быть в диапазоне от 60 до 245"
      );
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await onSave(score);
      onClose();
    } catch (err: any) {
      setError(err.message || (lang === "ky" ? "Сактоодо ката кетти" : "Ошибка сохранения"));
    } finally {
      setSaving(false);
    }
  };

  const getTierInfo = (s: number) => {
    if (s >= 219) {
      return {
        badge: lang === "ky" ? "Алтын Сертификат" : "Золотой Сертификат",
        desc: lang === "ky" ? "Топ-50 республикалык жеңүүчүлөр" : "Топ-50 лучших абитуриентов страны",
        color: "text-amber-700 bg-amber-50 border-amber-300",
        icon: Award,
      };
    }
    if (s >= 175) {
      return {
        badge: lang === "ky" ? "Бюджеттик грант" : "Бюджетный грант",
        desc: lang === "ky" ? "Мамлекеттик жогорку окуу жайларга грант" : "Бесплатное обучение в ведущих вузах",
        color: "text-emerald-700 bg-emerald-50 border-emerald-300",
        icon: GraduationCap,
      };
    }
    if (s >= 140) {
      return {
        badge: lang === "ky" ? "Контракттык орун" : "Контрактное место",
        desc: lang === "ky" ? "Көпчүлүк престиждүү факультеттер" : "Доступ к большинству факультетов",
        color: "text-blue-700 bg-blue-50 border-blue-300",
        icon: BookOpen,
      };
    }
    return {
      badge: lang === "ky" ? "Босого баллдан өттү" : "Пороговый уровень",
      desc: lang === "ky" ? "ЖОЖдорго тапшырууга укук (110+)" : "Право подачи в вузы (110+)",
      color: "text-slate-700 bg-slate-50 border-slate-300",
      icon: Check,
    };
  };

  const currentTier = getTierInfo(score);
  const TierIcon = currentTier.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-xs p-4 animate-in fade-in">
      <div className="bg-white w-full max-w-md rounded-3xl shadow-2xl border border-slate-200 overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
              <Target className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-sm">
                {lang === "ky" ? "Максаттуу баллды коюу" : "Изменить целевой балл"}
              </h3>
              <p className="text-[11px] text-slate-400">
                {lang === "ky" ? "ОРТ нормативдик шкаласы: 60 — 245" : "Шкала ОРТ: 60 — 245 баллов"}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {error && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Score Numeric Input */}
          <div className="text-center space-y-2 py-1">
            <label className="text-xs font-semibold text-slate-500 block">
              {lang === "ky" ? "Сиздин максатыңыз (балл)" : "Ваша цель (баллов)"}
            </label>
            <div className="inline-flex items-center justify-center">
              <input
                type="number"
                min={60}
                max={245}
                required
                value={isNaN(score) ? "" : score}
                onChange={(e) => setScore(parseInt(e.target.value, 10))}
                className="w-32 py-2 text-center text-4xl font-extrabold text-slate-900 bg-slate-50 border-2 border-emerald-500/50 rounded-2xl focus:border-emerald-600 focus:outline-none focus:bg-white tracking-tight"
              />
            </div>
          </div>

          {/* Tier Feedback Card */}
          <div className={`p-3.5 rounded-2xl border flex items-center gap-3 ${currentTier.color}`}>
            <TierIcon className="w-5 h-5 flex-shrink-0" />
            <div className="text-xs min-w-0 flex-1">
              <span className="font-bold block truncate">{currentTier.badge}</span>
              <span className="text-[11px] opacity-80 block truncate">{currentTier.desc}</span>
            </div>
          </div>

          {/* Quick Targets Suggestions */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
              {lang === "ky" ? "Көп тандалган максаттар:" : "Популярные цели:"}
            </span>
            <div className="grid grid-cols-4 gap-2">
              {[
                { val: 145, label: "145" },
                { val: 175, label: "175" },
                { val: 200, label: "200" },
                { val: 220, label: "220 ⭐" },
              ].map((item) => (
                <button
                  key={item.val}
                  type="button"
                  onClick={() => handleQuickSelect(item.val)}
                  className={`py-1.5 px-2 text-xs font-semibold rounded-xl border transition ${
                    score === item.val
                      ? "bg-slate-900 text-white border-slate-900 shadow-2xs"
                      : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-xl transition"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl shadow-xs transition disabled:opacity-50"
            >
              {saving
                ? (lang === "ky" ? "Сакталууда..." : "Сохранение...")
                : (lang === "ky" ? "Сактоо" : "Сохранить")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default TargetScoreModal;
