"use client";

import React from "react";
import { NumberedPassage } from "@/components/lms/NumberedPassage";
import type { StudentPassage } from "@/lib/lms/attemptTypes";

export function PassagePane({ passage }: { passage: StudentPassage }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs lg:max-h-[calc(100vh-11rem)] lg:overflow-y-auto">
      {passage.title ? <h2 className="mb-3 text-base font-bold text-slate-900">{passage.title}</h2> : null}
      {passage.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={passage.image_url} alt="" className="mb-3 max-h-72 w-auto rounded-lg" />
      ) : null}
      <NumberedPassage text={passage.body} />
    </section>
  );
}
