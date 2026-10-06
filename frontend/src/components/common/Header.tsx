"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Globe, Menu } from "lucide-react";

interface HeaderProps {
  title?: string;
  subtitle?: string;
  onMenuClick?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle, onMenuClick }) => {
  const { lang, setLang } = useTranslation();

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center gap-3">
        {onMenuClick && (
          <button
            type="button"
            onClick={onMenuClick}
            className="md:hidden p-2 -ml-1 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition focus:outline-none cursor-pointer"
            aria-label="Open navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}
        <div>
          {title && <h1 className="text-xl font-bold text-slate-900 tracking-tight">{title}</h1>}
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
      </div>

      <div className="flex items-center space-x-4">
        {/* Language Switcher Button */}
        <div className="flex items-center bg-slate-100 p-1 rounded-lg border border-slate-200">
          <Globe className="w-3.5 h-3.5 text-slate-500 ml-1.5 mr-1" />
          <button
            onClick={() => setLang("ky")}
            className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
              lang === "ky"
                ? "bg-white text-brand-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Кыргызча
          </button>
          <button
            onClick={() => setLang("ru")}
            className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
              lang === "ru"
                ? "bg-white text-brand-600 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Русский
          </button>
        </div>
      </div>
    </header>
  );
};

