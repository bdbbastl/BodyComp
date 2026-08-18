import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  // Wird von backend/app/routers/auth.py's google_callback gesetzt, wenn
  // authorize_access_token() fehlschlägt (z.B. abgelaufener/doppelt
  // gestarteter Login-Versuch) - statt eines rohen 500 landet der Nutzer
  // hier mit einer verständlichen Meldung statt eines stillen Fehlschlags.
  const googleOAuthFailed = searchParams.get("error") === "google_oauth_failed";

  const loginMutation = useMutation({
    mutationFn: () => api.auth.login(email, password),
    onSuccess: (user) => {
      queryClient.setQueryData(["auth", "me"], user);
      // "/app" wird über ClientRedirect ausgewertet, das bereits beide
      // Kontotypen korrekt behandelt (coach -> Dashboard, single -> das
      // eine Client-Profil) - kein eigener Pfad pro Kontotyp nötig.
      navigate("/app");
    },
  });

  const resendMutation = useMutation({
    mutationFn: () => api.auth.resendVerification(email),
  });

  const isUnverifiedError =
    loginMutation.isError &&
    (loginMutation.error as any)?.response?.status === 403;

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
          Password
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        {googleOAuthFailed && (
          <p className="text-sm text-red-400">
            Google sign-in didn't complete - please try again.
          </p>
        )}
        {isUnverifiedError ? (
          <div className="text-sm text-red-400">
            <p>Please confirm your email address first.</p>
            <button
              type="button"
              onClick={() => resendMutation.mutate()}
              disabled={resendMutation.isPending}
              className="mt-1 text-accent hover:underline disabled:opacity-50"
            >
              {resendMutation.isSuccess ? "Email resent" : "Resend confirmation email"}
            </button>
          </div>
        ) : (
          loginMutation.isError && (
            <p className="text-sm text-red-400">Email or password incorrect.</p>
          )
        )}
        <button
          type="submit"
          disabled={loginMutation.isPending}
          className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {loginMutation.isPending ? "Logging in…" : "Log in"}
        </button>
        <a
          href="/api/auth/google/login"
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-black/30 px-4 py-2 text-sm font-medium text-white hover:bg-black/50"
        >
          Sign in with Google
        </a>
        <div className="flex justify-between text-sm">
          <Link to="/signup" className="text-accent hover:underline">
            Sign up
          </Link>
          <Link to="/forgot-password" className="text-accent hover:underline">
            Forgot password?
          </Link>
        </div>
      </form>
    </div>
  );
}
