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
        <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
          <p className="text-slate-400">Invalid link.</p>
          <Link to="/forgot-password" className="block text-sm text-accent hover:underline">
            Request new link
          </Link>
          <Link to="/login" className="block text-sm text-accent hover:underline">
            Back to login
          </Link>
        </div>
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
        <h1 className="text-xl font-semibold text-white">Set new password</h1>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          New password (min. 8 characters)
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
          <p className="text-sm text-red-400">Link invalid or expired.</p>
        )}
        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {mutation.isPending ? "Saving…" : "Set password"}
        </button>
        <Link to="/login" className="block text-center text-sm text-accent hover:underline">
          Back to login
        </Link>
      </form>
    </div>
  );
}
