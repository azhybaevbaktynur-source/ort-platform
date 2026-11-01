import React from "react";

/**
 * The policy files (`backend/app/lms/privacy/policies/*.md`) use headings, paragraphs and `-` lists only. They become
 * React elements line by line: no HTML is ever injected.
 */
export function PolicyBody({ body }: { body: string }) {
  const out: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length === 0) return;
    out.push(<ul key={out.length} className="mt-3 list-disc space-y-1 pl-5">{list.map((x, i) => <li key={i}>{x}</li>)}</ul>);
    list = [];
  };
  for (const raw of body.split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    if (!line) continue;
    if (line.startsWith("# ")) out.push(<h1 key={out.length} className="text-2xl font-bold tracking-tight text-slate-900">{line.slice(2)}</h1>);
    else if (line.startsWith("## ")) out.push(<h2 key={out.length} className="mt-6 text-lg font-semibold text-slate-900">{line.slice(3)}</h2>);
    else out.push(<p key={out.length} className="mt-3">{line}</p>);
  }
  flush();
  return <div className="break-words text-base leading-7 text-slate-800">{out}</div>;
}
