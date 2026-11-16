import type { ReactNode } from "react";

export const card = "rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900";

const tones: Record<string, string> = {
  booked: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  escalated: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  open: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  claimed: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  closed: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  denied: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  error: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export function Badge({ value }: { value: string | null }) {
  if (!value) return <span className="text-slate-400">—</span>;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tones[value] ?? "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}>{value}</span>;
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={card}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {children}
    </section>
  );
}

export const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
export const secs = (a: string, b: string | null) => (b ? `${Math.round((+new Date(b) - +new Date(a)) / 1000)}s` : "—");
