import { Link } from "react-router-dom";

export default function LegalPagePlaceholder({ title }: { title: string }) {
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 text-slate-300">
      <div className="mb-4 rounded-lg border border-yellow-600/40 bg-yellow-950/20 p-3 text-sm text-yellow-400">
        ENTWURF — dieser Text muss vor echtem Live-Betrieb rechtlich geprüft werden.
      </div>
      <h1 className="mb-4 text-2xl font-semibold text-white">{title}</h1>
      <p className="text-slate-400">
        Platzhaltertext. Wird vor öffentlichem Launch durch rechtsverbindlichen Inhalt ersetzt.
      </p>
      <Link to="/login" className="mt-6 inline-block text-accent hover:underline">
        Zurück
      </Link>
    </div>
  );
}
