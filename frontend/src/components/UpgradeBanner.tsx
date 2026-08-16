import { Link } from "react-router-dom";

export function UpgradeBanner({
  message,
  ctaLabel = "Jetzt upgraden",
}: {
  message: string;
  ctaLabel?: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-accent/20 bg-accent/10 px-4 py-2 text-sm sm:px-6">
      <span className="text-slate-200">{message}</span>
      <Link to="/account" className="shrink-0 font-medium text-accent hover:underline">
        {ctaLabel} →
      </Link>
    </div>
  );
}
