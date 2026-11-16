import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type CallDetail, type Staff } from "../api";
import { Badge, Section, secs, when } from "../components/ui";

const STAGES = [
  { key: "stt_ms", label: "Speech to text", color: "bg-sky-500" },
  { key: "llm_ms", label: "LLM first token", color: "bg-violet-500" },
  { key: "tts_ms", label: "Text to speech", color: "bg-emerald-500" },
] as const;

export default function CallDetailPage({ staff }: { staff: Staff }) {
  const { id } = useParams();
  const [reveal, setReveal] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ["call", id, reveal],
    queryFn: () => api<CallDetail>(`/staff/calls/${id}${reveal ? "?reveal=true" : ""}`),
  });

  if (isLoading) return <p className="text-slate-500">Loading call…</p>;
  if (error || !data) return <p role="alert" className="text-red-600">Could not load this call.</p>;

  const maxMs = Math.max(1, ...data.latency.map((l) => l.total_ms ?? 0));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/calls" className="text-sm text-sky-700 hover:underline dark:text-sky-400">← All calls</Link>
          <h2 className="mt-1 text-xl font-semibold">Call #{data.id} <Badge value={data.outcome} /></h2>
          <p className="text-sm text-slate-500">{when(data.started_at)} · {secs(data.started_at, data.ended_at)} · {data.channel} · {data.verified ? "caller verified" : "caller not verified"}</p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${data.masked ? "bg-slate-200 dark:bg-slate-800" : "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"}`}>
            {data.masked ? "Personal details masked" : "Unmasked view (logged)"}
          </span>
          {staff.role === "admin" && (
            <button onClick={() => setReveal((r) => !r)} className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">
              {reveal ? "Mask again" : "Reveal"}
            </button>
          )}
        </div>
      </div>

      {(data.appointment || data.handoff) && (
        <div className="grid gap-4 md:grid-cols-2">
          {data.appointment && (
            <Section title="Booking">
              <p className="font-medium">{when(data.appointment.start_time)} with {data.appointment.provider}</p>
              <p className="text-sm text-slate-500">Appointment #{data.appointment.id}{data.appointment.reason ? ` · ${data.appointment.reason}` : ""}</p>
            </Section>
          )}
          {data.handoff && (
            <Section title="Handoff">
              <p className="font-medium">{data.handoff.reason} <Badge value={data.handoff.status} /></p>
              <Link to="/handoffs" className="text-sm text-sky-700 hover:underline dark:text-sky-400">Open the handoff queue</Link>
            </Section>
          )}
        </div>
      )}

      <Section title="Transcript">
        {data.transcript.length === 0 ? <p className="text-sm text-slate-500">No transcript was stored for this call.</p> : (
          <ol className="space-y-2">
            {data.transcript.map((t) => (
              <li key={t.idx} className={`flex ${t.role === "user" ? "justify-start" : "justify-end"}`}>
                <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${t.role === "user" ? "bg-slate-100 dark:bg-slate-800" : "bg-sky-100 dark:bg-sky-950"}`}>
                  <p className="mb-0.5 text-xs uppercase tracking-wide text-slate-500">{t.role === "user" ? "Caller" : "Agent"}{t.interrupted ? " · interrupted" : ""}</p>
                  {t.text}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Section>

      <Section title="Reply latency per turn">
        {data.latency.length === 0 ? <p className="text-sm text-slate-500">No audio replies were timed (text-only evals have none).</p> : (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-4 text-xs text-slate-500">
              {STAGES.map((s) => <span key={s.key} className="flex items-center gap-1"><span className={`inline-block h-2 w-2 rounded-sm ${s.color}`} />{s.label}</span>)}
            </div>
            {data.latency.map((l, i) => (
              <div key={l.idx} className="flex items-center gap-3 text-xs">
                <span className="w-14 shrink-0 text-slate-500">Turn {i + 1}</span>
                <div className="flex h-4 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
                  {STAGES.map((s) => <div key={s.key} className={s.color} style={{ width: `${((l[s.key] ?? 0) / maxMs) * 100}%` }} title={`${s.label}: ${l[s.key] ?? "?"} ms`} />)}
                </div>
                <span className="w-16 shrink-0 text-right tabular-nums">{l.total_ms} ms</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Tool calls">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500"><tr><th className="py-1 pr-4">Tool</th><th className="pr-4">Status</th><th className="pr-4">Latency</th><th>Result</th></tr></thead>
            <tbody>
              {data.tool_calls.map((t, i) => (
                <tr key={i} className="border-t border-slate-100 align-top dark:border-slate-800">
                  <td className="py-2 pr-4 font-mono text-xs">{t.name}</td>
                  <td className="pr-4"><Badge value={t.status} /></td>
                  <td className="pr-4 tabular-nums">{t.latency_ms ?? "—"} ms</td>
                  <td className="font-mono text-xs text-slate-500">{JSON.stringify(t.result)}</td>
                </tr>
              ))}
              {data.tool_calls.length === 0 && <tr><td colSpan={4} className="py-2 text-slate-500">No tool calls.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
