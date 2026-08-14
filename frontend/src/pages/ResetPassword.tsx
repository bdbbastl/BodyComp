import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: () => api.auth.resetPassword(token, password),
    onSuccess: () => navigate("/login"),
  });

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <p className="text-slate-400">Ungültiger Link.</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
        className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6"
      >
        <h1 className="text-xl font-semibold text-white">Neues Passwort setzen</h1>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Neues Passwort (mind. 8 Zeichen)
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        {mutation.isError && (
          <p className="text-sm text-red-400">Link ungültig oder abgelaufen.</p>
        )}
        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {mutation.isPending ? "Speichern…" : "Passwort setzen"}
        </button>
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Zurück zum Login
        </Link>
      </form>
    </div>
  );
}
