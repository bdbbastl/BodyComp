import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const loginMutation = useMutation({
    mutationFn: () => api.auth.login(email, password),
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
      navigate(user.account_type === "coach" ? "/" : "/redirect-to-my-client");
    },
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          loginMutation.mutate();
        }}
        className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6"
      >
        <h1 className="text-xl font-semibold text-white">
          BodyComp <span className="text-accent">Tracker</span>
        </h1>
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
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Passwort
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        {loginMutation.isError && (
          <p className="text-sm text-red-400">E-Mail oder Passwort falsch.</p>
        )}
        <button
          type="submit"
          disabled={loginMutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {loginMutation.isPending ? "Einloggen…" : "Einloggen"}
        </button>
      </form>
    </div>
  );
}
