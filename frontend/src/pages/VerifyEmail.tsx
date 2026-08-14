import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../api/client";

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    api.auth
      .verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        {status === "pending" && <p className="text-slate-400">Bestätige…</p>}
        {status === "success" && (
          <>
            <h1 className="text-xl font-semibold text-white">E-Mail bestätigt!</h1>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Jetzt einloggen
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <h1 className="text-xl font-semibold text-white">Link ungültig</h1>
            <p className="text-sm text-slate-400">
              Der Link ist abgelaufen oder wurde bereits verwendet.
            </p>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Zurück zum Login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
