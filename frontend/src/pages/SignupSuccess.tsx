import { Link } from "react-router-dom";

export default function SignupSuccess() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        <h1 className="text-xl font-semibold text-white">Fast geschafft!</h1>
        <p className="text-sm text-slate-400">
          Wir haben dir eine E-Mail geschickt. Bitte klicke auf den Bestätigungslink, um dein
          Konto zu aktivieren.
        </p>
        <Link to="/login" className="text-accent hover:underline text-sm">
          Zurück zum Login
        </Link>
      </div>
    </div>
  );
}
