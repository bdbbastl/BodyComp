import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "../api/client";

export default function ConfirmEmailChange() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [newEmail, setNewEmail] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    api.auth
      .confirmEmailChange(token)
      .then((data) => {
        setNewEmail(data.new_email);
        setStatus("success");
      })
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        {status === "pending" && <p className="text-slate-400">Confirming…</p>}
        {status === "success" && (
          <>
            <h1 className="text-xl font-semibold text-white">Email updated!</h1>
            <p className="text-sm text-slate-400">
              Your login email is now <span className="text-white">{newEmail}</span>.
            </p>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Continue
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <h1 className="text-xl font-semibold text-white">Invalid link</h1>
            <p className="text-sm text-slate-400">
              The link has expired or was already used.
            </p>
            <Link to="/login" className="text-accent hover:underline text-sm">
              Back to login
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
