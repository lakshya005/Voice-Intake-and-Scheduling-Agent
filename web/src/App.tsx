import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ApiError, api, type Staff } from "./api";
import AccessLog from "./pages/AccessLog";
import CallDetailPage from "./pages/CallDetail";
import Calls from "./pages/Calls";
import Handoffs from "./pages/Handoffs";
import Login from "./pages/Login";

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800"}`;

export default function App() {
  const qc = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Staff>("/staff/me"),
    retry: (_, err) => !(err instanceof ApiError && err.status === 401),
  });

  if (me.isLoading) return <p className="p-8 text-slate-500">Loading…</p>;
  if (!me.data) return <Login onLoggedIn={() => qc.invalidateQueries({ queryKey: ["me"] })} />;

  const staff = me.data;
  const logout = async () => {
    await api("/staff/logout", { method: "POST" });
    qc.clear();
    qc.invalidateQueries({ queryKey: ["me"] });
  };

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16">
      <header className="flex flex-wrap items-center justify-between gap-3 py-5">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">Voice Intake · Staff</h1>
          <nav className="flex gap-1">
            <NavLink to="/calls" className={link}>Calls</NavLink>
            <NavLink to="/handoffs" className={link}>Handoffs</NavLink>
            {staff.role === "admin" && <NavLink to="/access-log" className={link}>Access log</NavLink>}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
          <span>{staff.username} <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs dark:bg-slate-800">{staff.role}</span></span>
          <button onClick={logout} className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">Log out</button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/calls" replace />} />
          <Route path="/calls" element={<Calls />} />
          <Route path="/calls/:id" element={<CallDetailPage staff={staff} />} />
          <Route path="/handoffs" element={<Handoffs staff={staff} />} />
          <Route path="/access-log" element={staff.role === "admin" ? <AccessLog /> : <Navigate to="/calls" replace />} />
        </Routes>
      </main>
    </div>
  );
}
