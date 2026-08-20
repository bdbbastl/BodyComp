import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const navigate = useNavigate();

  const signupMutation = useMutation({
    mutationFn: () =>
      api.auth.signup({ email, password, display_name: displayName, privacy_accepted: privacyAccepted }),
    onSuccess: () => navigate("/signup-success"),
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          signupMutation.mutate();
        }}
        className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6"
      >
        <h1 className="text-xl font-semibold text-white">
          BodyComp <span className="text-accent">Tracker</span>
        </h1>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Name
          <input
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Password (min. 8 characters)
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex items-start gap-2 text-sm text-slate-400">
          <input
            type="checkbox"
            required
            checked={privacyAccepted}
            onChange={(e) => setPrivacyAccepted(e.target.checked)}
            className="mt-1"
          />
          <span>
            I accept the{" "}
            <Link to="/datenschutz" className="text-accent hover:underline" target="_blank">
              privacy policy
            </Link>
          </span>
        </label>
        {signupMutation.isError && (
          <p className="text-sm text-red-400">
            {(signupMutation.error as any)?.response?.status === 409
              ? "This email address is already registered."
              : (signupMutation.error as any)?.response?.status === 503
                ? "Could not send the confirmation email. Please try again shortly."
                : "Sign-up failed. Please try again."}
          </p>
        )}
        <button
          type="submit"
          disabled={signupMutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {signupMutation.isPending ? "Signing up…" : "Sign up"}
        </button>
        <p className="text-center text-sm text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Log in
          </Link>
        </p>
      </form>
    </div>
  );
}
