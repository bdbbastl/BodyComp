// frontend/src/pages/Landing.tsx
import { Link, Navigate } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";

const FEATURES = [
  {
    icon: "🔗",
    title: "Magic-link check-ins",
    body: "Clients submit weight and progress photos through a link - no account, no app download for them.",
  },
  {
    icon: "🤖",
    title: "AI-powered comparisons",
    body: "Get an objective before/after read on any two check-ins - muscle definition, symmetry, conditioning.",
  },
  {
    icon: "📈",
    title: "Timeline & stats",
    body: "Every check-in lands on a clean visual timeline with weight trends and progress photos side by side.",
  },
  {
    icon: "🔔",
    title: "Automatic reminders",
    body: "Set a check-in cadence once - BodyComp nudges whoever's falling behind, so you don't have to chase.",
  },
];

/** Öffentliche Marketing-Seite unter "/" - siehe Design-Spec
 * "Landingpage" Abschnitt "Routing-Umbau". Eingeloggte Nutzer werden
 * sofort zu /app weitergeleitet, sehen diese Seite nie. */
export default function Landing() {
  const { data: user, isLoading } = useCurrentUser();

  if (isLoading) return null;
  if (user) return <Navigate to="/app" replace />;

  return (
    <div className="min-h-screen bg-background text-slate-100">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="text-sm font-semibold tracking-wide text-white">
          BodyComp <span className="text-accent">Tracker</span>
        </span>
        <Link
          to="/login"
          className="text-sm font-medium text-slate-300 hover:text-white"
        >
          Log in
        </Link>
      </header>

      <section className="mx-auto max-w-4xl px-4 pb-20 pt-12 text-center sm:px-6 sm:pt-20">
        <h1 className="text-4xl font-bold leading-tight text-white sm:text-5xl">
          Run your coaching business,{" "}
          <span className="text-accent">not spreadsheets</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-400">
          Track every client's progress photos, weight, and check-ins in one place -
          or use it solo to track your own transformation.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/signup"
            className="rounded-lg bg-accent px-6 py-3 text-sm font-semibold text-slate-900 transition-opacity hover:opacity-90"
          >
            Start as a coach
          </Link>
          <Link
            to="/signup"
            className="rounded-lg border border-white/15 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/5"
          >
            Track yourself
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-white/5 bg-surface p-5"
            >
              <span className="text-2xl">{f.icon}</span>
              <p className="mt-3 text-sm font-semibold text-white">{f.title}</p>
              <p className="mt-1.5 text-sm text-slate-400">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 pb-20 sm:px-6">
        <h2 className="text-center text-2xl font-bold text-white">How it works</h2>
        <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-3">
          <HowItWorksStep
            number={1}
            title="Add a client"
            body="Create a client profile in seconds - or just start tracking yourself."
          />
          <HowItWorksStep
            number={2}
            title="Share the check-in link"
            body="Your client bookmarks their personal link and submits photos + weight whenever it's time."
          />
          <HowItWorksStep
            number={3}
            title="Review progress"
            body="See everything on a timeline, compare any two dates, leave feedback."
          />
        </div>
        <p className="mx-auto mt-6 max-w-md text-center text-xs text-slate-600">
          Solo tracking works the same way, minus the sharing step - it's just you and your own timeline.
        </p>
      </section>
    </div>
  );
}

function HowItWorksStep({ number, title, body }: { number: number; title: string; body: string }) {
  return (
    <div className="text-center">
      <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent">
        {number}
      </div>
      <p className="mt-3 text-sm font-semibold text-white">{title}</p>
      <p className="mt-1.5 text-sm text-slate-400">{body}</p>
    </div>
  );
}
