import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type Handoff, type PatientInfo, type Staff } from "../api";
import { Badge, Section, card, when } from "../components/ui";

const TABS = ["open", "claimed", "closed"] as const;

export default function Handoffs({ staff }: { staff: Staff }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof TABS)[number]>("open");
  const [patientFor, setPatientFor] = useState<number | null>(null);
  const list = useQuery({ queryKey: ["handoffs", tab], queryFn: () => api<Handoff[]>(`/staff/handoffs?status=${tab}`) });

  const act = useMutation({
    mutationFn: ({ id, verb }: { id: number; verb: "claim" | "close" }) => api(`/staff/handoffs/${id}/${verb}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["handoffs"] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`rounded-md px-3 py-1.5 text-sm capitalize ${tab === t ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-200 dark:hover:bg-slate-800"}`}>{t}</button>
        ))}
      </div>
      {act.error && <p role="alert" className="text-sm text-red-600">{(act.error as ApiError).message}</p>}
      {list.isLoading ? <p className="text-slate-500">Loading…</p> : !list.data?.length ? <p className="text-slate-500">Nothing {tab}.</p> : (
        <ul className="space-y-3">
          {list.data.map((h) => {
            const mine = h.claimed_by === staff.username || staff.role === "admin";
            return (
              <li key={h.id} className={card}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{h.reason} <Badge value={h.status} /></p>
                    <p className="text-sm text-slate-500">
                      {when(h.created_at)} · <Link className="text-sky-700 hover:underline dark:text-sky-400" to={`/calls/${h.call_id}`}>call #{h.call_id}</Link>
                      {" · "}{h.verified ? "caller was verified" : "caller was NOT verified"}{h.claimed_by ? ` · claimed by ${h.claimed_by}` : ""}
                    </p>
                  </div>
                  <div className="flex gap-2 text-sm">
                    {h.status === "open" && <button onClick={() => act.mutate({ id: h.id, verb: "claim" })} className="rounded-md bg-slate-900 px-3 py-1.5 text-white dark:bg-slate-100 dark:text-slate-900">Claim</button>}
                    {h.status === "claimed" && mine && <button onClick={() => setPatientFor(patientFor === h.id ? null : h.id)} className="rounded-md border border-slate-300 px-3 py-1.5 dark:border-slate-700">{patientFor === h.id ? "Hide patient" : "Open patient"}</button>}
                    {h.status === "claimed" && mine && <button onClick={() => act.mutate({ id: h.id, verb: "close" })} className="rounded-md border border-slate-300 px-3 py-1.5 dark:border-slate-700">Close</button>}
                  </div>
                </div>
                {patientFor === h.id && <PatientPanel handoffId={h.id} />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function PatientPanel({ handoffId }: { handoffId: number }) {
  const { data, error, isLoading } = useQuery({ queryKey: ["patient", handoffId], queryFn: () => api<PatientInfo>(`/staff/handoffs/${handoffId}/patient`), gcTime: 0 });
  return (
    <div className="mt-3">
      <Section title="Patient (this view is logged)">
        {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {error && <p role="alert" className="text-sm text-amber-700 dark:text-amber-400">{(error as ApiError).message}</p>}
        {data && (
          <div className="space-y-2 text-sm">
            <p className="font-medium">{data.first_name} {data.last_name} · born {data.dob}{data.phone ? ` · ${data.phone}` : ""}</p>
            <ul className="list-disc pl-5 text-slate-600 dark:text-slate-300">
              {data.recent_visits.map((v) => <li key={v.date + v.reason}>{v.date} · {v.provider} · {v.reason}</li>)}
              {data.recent_visits.length === 0 && <li>No past visits on record.</li>}
            </ul>
          </div>
        )}
      </Section>
    </div>
  );
}
