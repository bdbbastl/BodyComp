import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const mutation = useMutation({ mutationFn: () => api.auth.forgotPassword(email) });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6">
        <h1 className="text-xl font-semibold text-white">Passwort vergessen</h1>
        {mutation.isSuccess ? (
          <p className="text-sm text-slate-400">
            Falls ein Account mit dieser E-Mail existiert, wurde eine Mail mit einem Reset-Link
            verschickt.
          </p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate();
            }}
            className="space-y-4"
          >
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              E-Mail
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
            >
              {mutation.isPending ? "Senden…" : "Link anfordern"}
            </button>
          </form>
        )}
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Zurück zum Login
        </Link>
      </div>
    </div>
  );
}
