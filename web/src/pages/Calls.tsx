import { useQuery } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type SortingState } from "@tanstack/react-table";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type CallRow } from "../api";
import { Badge, card, secs, when } from "../components/ui";

const col = createColumnHelper<CallRow>();

const columns = [
  col.accessor("id", { header: "Call", cell: (c) => <Link className="font-medium text-sky-700 hover:underline dark:text-sky-400" to={`/calls/${c.getValue()}`}>#{c.getValue()}</Link> }),
  col.accessor("started_at", { header: "Started", cell: (c) => when(c.getValue()) }),
  col.display({ id: "duration", header: "Duration", cell: (c) => secs(c.row.original.started_at, c.row.original.ended_at) }),
  col.accessor("channel", { header: "Channel" }),
  col.accessor("outcome", { header: "Outcome", cell: (c) => <Badge value={c.getValue()} /> }),
  col.accessor("handoff_status", { header: "Handoff", cell: (c) => <Badge value={c.getValue()} /> }),
  col.accessor("turns", { header: "Turns" }),
  col.accessor("p50_ms", { header: "Median reply", cell: (c) => (c.getValue() == null ? "—" : `${c.getValue()} ms`) }),
];

export default function Calls() {
  const { data, isLoading, error } = useQuery({ queryKey: ["calls"], queryFn: () => api<CallRow[]>("/staff/calls?limit=100") });
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({ data: data ?? [], columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });

  if (isLoading) return <p className="text-slate-500">Loading calls…</p>;
  if (error) return <p role="alert" className="text-red-600">Could not load calls.</p>;
  if (!data?.length) return <p className="text-slate-500">No calls yet.</p>;

  return (
    <div className={`${card} overflow-x-auto p-0`}>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
          {table.getHeaderGroups().map((g) => (
            <tr key={g.id}>
              {g.headers.map((h) => (
                <th key={h.id} className="cursor-pointer select-none px-4 py-3" onClick={h.column.getToggleSortingHandler()}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
              {r.getVisibleCells().map((c) => <td key={c.id} className="px-4 py-3">{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
