import { useState } from "react";
import { ApiError, api } from "../api";
import { card } from "../components/ui";

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/staff/login", { json: { username, password } });
      onLoggedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
    }
  };

  return (
    <div className="mx-auto mt-24 max-w-sm px-4">
      <form onSubmit={submit} className={`${card} space-y-4`}>
        <h1 className="text-lg font-semibold">Staff sign in</h1>
        <p className="text-sm text-slate-500">Synthetic data only. Every view is recorded in the access log.</p>
        <label className="block text-sm">
          Username
          <input className="mt-1 w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" />
        </label>
        <label className="block text-sm">
          Password
          <input type="password" className="mt-1 w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900">Sign in</button>
      </form>
    </div>
  );
}
