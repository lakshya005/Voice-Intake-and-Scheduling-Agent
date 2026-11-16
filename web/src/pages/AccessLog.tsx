import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type AccessEntry } from "../api";
import { card, when } from "../components/ui";

export default function AccessLog() {
  const { data, isLoading } = useQuery({ queryKey: ["access-log"], queryFn: () => api<AccessEntry[]>("/staff/access-log?limit=200") });
  if (isLoading) return <p className="text-slate-500">Loading…</p>;
  return (
    <div className={`${card} overflow-x-auto p-0`}>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800"><tr><th className="px-4 py-3">When</th><th>Who</th><th>Action</th><th>Call</th></tr></thead>
        <tbody>
          {data?.map((e) => (
            <tr key={e.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
              <td className="px-4 py-2">{when(e.at)}</td>
              <td>{e.staff}</td>
              <td className="font-mono text-xs">{e.action}</td>
              <td>{e.call_id ? <Link className="text-sky-700 hover:underline dark:text-sky-400" to={`/calls/${e.call_id}`}>#{e.call_id}</Link> : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
