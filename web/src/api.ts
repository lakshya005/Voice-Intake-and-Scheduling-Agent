export type Staff = { username: string; role: "admin" | "agent" };

export type CallRow = {
  id: number; started_at: string; ended_at: string | null; channel: string; outcome: string | null;
  turns: number; p50_ms: number | null; handoff_status: string | null;
};

export type CallDetail = {
  id: number; started_at: string; ended_at: string | null; channel: string; outcome: string | null;
  verified: boolean; masked: boolean;
  transcript: { idx: number; role: "user" | "assistant"; text: string; interrupted: boolean }[];
  latency: { idx: number; stt_ms: number | null; llm_ms: number | null; tts_ms: number | null; total_ms: number | null }[];
  tool_calls: { name: string; status: string; latency_ms: number | null; args: unknown; result: unknown }[];
  appointment: { id: number; start_time: string; provider: string; reason: string | null } | null;
  handoff: { id: number; reason: string; status: string } | null;
};

export type Handoff = {
  id: number; call_id: number; reason: string; status: "open" | "claimed" | "closed";
  created_at: string; claimed_by: string | null; verified: boolean;
};

export type PatientInfo = {
  first_name: string; last_name: string; dob: string; phone: string | null;
  recent_visits: { date: string; provider: string; reason: string }[];
};

export type AccessEntry = { id: number; at: string; staff: string; action: string; call_id: number | null; detail: unknown };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const res = await fetch(path, {
    method: init?.method ?? (init?.json !== undefined ? "POST" : "GET"),
    headers: init?.json !== undefined ? { "content-type": "application/json" } : undefined,
    body: init?.json !== undefined ? JSON.stringify(init.json) : undefined,
    credentials: "same-origin",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
  }
  return res.json();
}
