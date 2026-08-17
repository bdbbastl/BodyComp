import { Link } from "react-router-dom";

export default function SignupSuccess() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-white/5 bg-surface p-6 text-center">
        <h1 className="text-xl font-semibold text-white">Almost there!</h1>
        <p className="text-sm text-slate-400">
          We've sent you an email. Please click the confirmation link to activate your
          account.
        </p>
        <Link to="/login" className="text-accent hover:underline text-sm">
          Back to login
        </Link>
      </div>
    </div>
  );
}
