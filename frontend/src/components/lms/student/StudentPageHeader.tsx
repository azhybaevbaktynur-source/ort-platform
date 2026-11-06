import React from "react";

/*
 * Student UI U8 (STUDENT_UI_DESIGN §5.1 d): the student pages' one header pattern, as on the Тесты page: the title, the
 * course (or a short line) under it, at most one action.
 */
export function StudentPageHeader({ title, subtitle, action, id }: {
  title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; id?: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="min-w-0 flex-1 basis-64">
        <h1 id={id} className="break-words text-2xl font-bold leading-8 text-slate-900 lg:text-[28px] lg:leading-9">{title}</h1>
        {subtitle ? <p className="mt-1 break-words text-sm leading-5 text-slate-600">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}
