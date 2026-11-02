"use client";

import React from "react";
import { Mascot, LinkButton } from "@/components/ui";
import { useStaticText } from "./staticText";

/** 404 page body (root and `[lang]` not-found): works without the language providers. */
export function NotFoundView() {
  const { lang, m } = useStaticText();
  return (
    <main className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-4 py-10 text-center">
      <Mascot pose="thinking" size={96} className="mb-3" />
      <h1 className="text-xl font-bold text-slate-900">{m.notFound.title}</h1>
      <p className="mt-1 text-sm leading-6 text-slate-600">{m.notFound.body}</p>
      <div className="mt-5"><LinkButton href={`/${lang}`}>{m.notFound.home}</LinkButton></div>
    </main>
  );
}
