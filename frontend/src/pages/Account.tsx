import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { DisplaySettings } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";
import PageHeader from "../components/PageHeader";
import { Card } from "../components/Card";
import { useOnboarding } from "../contexts/OnboardingContext";

const COLUMNS_MAX_LIMIT = 10;
const WEEKS_PER_PAGE_LIMIT = 25;

/** Anzeige-Einstellungen für die Timeline: max. Spaltenzahl im Foto-Grid
 * pro Tag und wie viele Tages-Gruppen ("Wochen") pro Seite gezeigt werden,
 * bevor Pagination greift. In der DB gespeichert (siehe
 * routers/settings.py), gilt also geräteübergreifend. */
function DisplaySettingsSection() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["settings", "display"],
    queryFn: api.settings.getDisplay,
  });

  const [columnsMax, setColumnsMax] = useState(5);
  const [weeksPerPage, setWeeksPerPage] = useState(8);

  useEffect(() => {
    if (statusQuery.data) {
      setColumnsMax(statusQuery.data.timeline_columns_max);
      setWeeksPerPage(statusQuery.data.timeline_weeks_per_page);
    }
  }, [statusQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (payload: DisplaySettings) => api.settings.setDisplay(payload),
    // Cache direkt mit der Server-Antwort befüllen statt nur zu
    // invalidieren: invalidateQueries refetcht standardmäßig nur AKTIVE
    // (gemountete) Queries - die Timeline war zum Zeitpunkt des Speicherns
    // ja gerade nicht sichtbar, ihre Query damit "inactive". Ohne
    // setQueryData bekam sie den neuen Wert dadurch teils erst bei einem
    // zufälligen späteren Refetch (staleTime/Fokus-Wechsel) statt sofort
    // beim nächsten Navigieren dorthin.
    onSuccess: (data) => {
      queryClient.setQueryData(["settings", "display"], data);
      queryClient.invalidateQueries({ queryKey: ["settings", "display"] });
    },
  });

  const dirty =
    !!statusQuery.data &&
    (statusQuery.data.timeline_columns_max !== columnsMax ||
      statusQuery.data.timeline_weeks_per_page !== weeksPerPage);

  return (
    <Card
      title="Display settings"
      description="Controls how the timeline is rendered - especially relevant for performance with lots of photos/days."
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Images side by side (max. {COLUMNS_MAX_LIMIT})
          <input
            type="number"
            min={1}
            max={COLUMNS_MAX_LIMIT}
            value={columnsMax}
            onChange={(e) =>
              setColumnsMax(Math.min(COLUMNS_MAX_LIMIT, Math.max(1, Number(e.target.value) || 1)))
            }
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Weeks per page (max. {WEEKS_PER_PAGE_LIMIT})
          <input
            type="number"
            min={1}
            max={WEEKS_PER_PAGE_LIMIT}
            value={weeksPerPage}
            onChange={(e) =>
              setWeeksPerPage(
                Math.min(WEEKS_PER_PAGE_LIMIT, Math.max(1, Number(e.target.value) || 1))
              )
            }
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
          />
        </label>
      </div>

      {dirty && (
        <button
          onClick={() =>
            saveMutation.mutate({ timeline_columns_max: columnsMax, timeline_weeks_per_page: weeksPerPage })
          }
          disabled={saveMutation.isPending}
          className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving…" : "Save"}
        </button>
      )}
    </Card>
  );
}

/** KI-Einstellungen: eigener Gemini-API-Key statt backend/.env-Bearbeitung.
 * Der Key wird nie im Klartext zurückgeliefert, nur ob/woher einer aktiv
 * ist (DB oder .env-Fallback) und die letzten 4 Zeichen zur Kontrolle. */
function GeminiKeySettings() {
  const queryClient = useQueryClient();
  const [inputValue, setInputValue] = useState("");
  const [editing, setEditing] = useState(false);

  const statusQuery = useQuery({
    queryKey: ["settings", "gemini-key"],
    queryFn: api.settings.getGeminiKey,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["settings", "gemini-key"] });

  const saveMutation = useMutation({
    mutationFn: (key: string) => api.settings.setGeminiKey(key),
    onSuccess: () => {
      setInputValue("");
      setEditing(false);
      invalidate();
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => api.settings.clearGeminiKey(),
    onSuccess: invalidate,
  });

  const status = statusQuery.data;

  return (
    <Card title="AI Settings">
      <p className="mb-4 text-sm text-slate-400">
        The AI judge analysis in Compare needs a free Gemini API key.
        Create one for free at{" "}
        <a
          href="https://aistudio.google.com/apikey"
          target="_blank"
          rel="noreferrer"
          className="text-accent underline"
        >
          aistudio.google.com/apikey
        </a>
        .
      </p>

      {!editing && status && (
        <div className="flex flex-wrap items-center gap-2">
          {status.configured ? (
            <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-slate-300">
              Active: ••••{status.last4}
              <span className="ml-1 text-slate-500">
                ({status.source === "settings" ? "your own key" : ".env fallback"})
              </span>
            </span>
          ) : (
            <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-slate-500">
              No key configured
            </span>
          )}
          <button
            onClick={() => setEditing(true)}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/10"
          >
            {status.configured ? "Change" : "Add key"}
          </button>
          {status.configured && status.source === "settings" && (
            <button
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
            >
              Remove
            </button>
          )}
        </div>
      )}

      {editing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (inputValue.trim()) saveMutation.mutate(inputValue.trim());
          }}
          className="flex flex-wrap items-center gap-2"
        >
          <input
            type="password"
            autoFocus
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Gemini API key"
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || saveMutation.isPending}
            className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(false);
              setInputValue("");
            }}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 hover:bg-white/10"
          >
            Cancel
          </button>
        </form>
      )}
      {saveMutation.isError && (
        <p className="mt-2 text-xs text-red-400">Could not save the key.</p>
      )}
    </Card>
  );
}

/** Zeigt E-Mail + Mitglied-seit-Datum, und - abhängig vom Account-Typ -
 * Formulare zum Ändern von Passwort und/oder E-Mail. Siehe Design-Spec
 * "Account-Profil-Verwaltung". */
function ProfileSection() {
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailRequested, setEmailRequested] = useState<string | null>(null);

  const changePasswordMutation = useMutation({
    mutationFn: () => api.auth.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setNewPasswordConfirm("");
      setPasswordSuccess(true);
    },
  });

  const changeEmailMutation = useMutation({
    mutationFn: () => api.auth.changeEmail(newEmail, emailPassword),
    onSuccess: () => {
      setEmailRequested(newEmail);
      setNewEmail("");
      setEmailPassword("");
      queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });

  if (!user) return null;

  const passwordsMismatch =
    newPassword.length > 0 && newPasswordConfirm.length > 0 && newPassword !== newPasswordConfirm;

  const memberSince = new Date(user.created_at).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-lg font-semibold text-white">{user.email}</p>
          <p className="text-sm text-slate-500">Member since {memberSince}</p>
        </div>
      </Card>

      {user.has_password && (
        <Card title="Change password">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setPasswordSuccess(false);
              if (!passwordsMismatch) changePasswordMutation.mutate();
            }}
            className="space-y-3"
          >
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Current password
              <input
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              New password
              <input
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Repeat new password
              <input
                type="password"
                required
                minLength={8}
                value={newPasswordConfirm}
                onChange={(e) => setNewPasswordConfirm(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
            {passwordsMismatch && (
              <p className="text-sm text-red-400">The new passwords don't match.</p>
            )}
            {changePasswordMutation.isError && (
              <p className="text-sm text-red-400">
                {(changePasswordMutation.error as any)?.response?.status === 401
                  ? "Current password is incorrect."
                  : "Could not change password."}
              </p>
            )}
            {passwordSuccess && <p className="text-sm text-accent">Password changed.</p>}
            <button
              type="submit"
              disabled={changePasswordMutation.isPending || passwordsMismatch}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
            >
              {changePasswordMutation.isPending ? "Saving…" : "Change password"}
            </button>
          </form>
        </Card>
      )}

      {!user.has_google_account && (
        <Card title="Change email">
          {emailRequested ? (
            <p className="text-sm text-slate-300">
              Check your inbox at <span className="text-white">{emailRequested}</span> to confirm
              the change.
            </p>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                changeEmailMutation.mutate();
              }}
              className="space-y-3"
            >
              <label className="flex flex-col gap-1 text-sm text-slate-400">
                New email address
                <input
                  type="email"
                  required
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm text-slate-400">
                Current password
                <input
                  type="password"
                  required
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                />
              </label>
              {changeEmailMutation.isError && (
                <p className="text-sm text-red-400">
                  {(changeEmailMutation.error as any)?.response?.status === 401
                    ? "Current password is incorrect."
                    : (changeEmailMutation.error as any)?.response?.status === 409
                      ? "This email address is already in use."
                      : "Could not change email."}
                </p>
              )}
              <button
                type="submit"
                disabled={changeEmailMutation.isPending}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
              >
                {changeEmailMutation.isPending ? "Sending…" : "Change email"}
              </button>
            </form>
          )}
        </Card>
      )}
    </>
  );
}

function DangerZoneSection() {
  const [showConfirm, setShowConfirm] = useState(false);
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const hasPassword = user?.has_password ?? true; // Default true, bis geladen: sicherer Default (Feld wird gezeigt, nicht versteckt)

  const deleteMutation = useMutation({
    mutationFn: () => api.auth.deleteAccount(password || undefined),
    onSuccess: () => {
      queryClient.clear();
      navigate("/login");
    },
  });

  const exportMutation = useMutation({
    mutationFn: api.auth.exportData,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "bodycomp-data-export.json";
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  return (
    <Card title="Account Management" danger>
      <div className="mt-3 flex flex-col gap-3">
        <button
          onClick={() => exportMutation.mutate()}
          disabled={exportMutation.isPending}
          className="w-fit rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-black/30"
        >
          {exportMutation.isPending ? "Exporting…" : "Export my data"}
        </button>

        {!showConfirm ? (
          <button
            onClick={() => setShowConfirm(true)}
            className="w-fit rounded-lg border border-red-900/50 px-4 py-2 text-sm text-red-400 hover:bg-red-950/30"
          >
            Delete account
          </button>
        ) : (
          <div className="space-y-2 rounded-lg border border-red-900/50 p-3">
            <p className="text-sm text-red-400">
              This will permanently delete your account and ALL associated data (clients, photos,
              history).
            </p>
            {hasPassword && (
              <input
                type="password"
                placeholder="Password to confirm"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
              />
            )}
            <div className="flex gap-2">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Deleting…" : "Delete permanently"}
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300"
              >
                Cancel
              </button>
            </div>
            {deleteMutation.isError && (
              <p className="text-sm text-red-400">
                {hasPassword ? "Deletion failed - is your password correct?" : "Deletion failed."}
              </p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

const COACH_PLANS: {
  key: "starter" | "pro" | "business";
  label: string;
  price: string;
  featured?: boolean;
  features: string[];
}[] = [
  {
    key: "starter",
    label: "Starter",
    price: "€19/month",
    features: ["Up to 5 clients", "Unlimited photos & check-ins", "Magic-link submission"],
  },
  {
    key: "pro",
    label: "Pro",
    price: "€49/month",
    featured: true,
    features: ["Up to 20 clients", "Everything in Starter", "Priority support"],
  },
  {
    key: "business",
    label: "Business",
    price: "€99/month",
    features: ["Unlimited clients", "Everything in Pro", "For large coaching teams"],
  },
];

function BillingSection() {
  const { data: user } = useCurrentUser();

  const checkoutMutation = useMutation({
    mutationFn: (tier: "starter" | "pro" | "business" | "single") => api.billing.checkout(tier),
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });

  const portalMutation = useMutation({
    mutationFn: api.billing.portal,
    onSuccess: (data) => {
      window.open(data.portal_url, "_blank");
    },
  });

  if (!user) return null;

  const hasSubscription = user.subscription_status === "trialing" || user.subscription_status === "active";
  const tierLabel = COACH_PLANS.find((p) => p.key === user.subscription_tier)?.label ?? user.subscription_tier;

  if (hasSubscription) {
    return (
      <div className="rounded-xl border border-accent/30 bg-gradient-to-br from-accent/10 to-transparent p-4">
        <h2 className="mb-1 text-lg font-semibold text-white">Your Subscription</h2>
        <p className="mb-4 text-sm text-slate-300">
          <span className="font-medium text-accent">{tierLabel}</span> —{" "}
          {user.subscription_status === "trialing" ? (
            <span>
              Trial in progress
              {user.trial_ends_at &&
                ` until ${new Date(user.trial_ends_at).toLocaleDateString("en-US")}`}
            </span>
          ) : (
            "active"
          )}
        </p>
        <button
          onClick={() => portalMutation.mutate()}
          disabled={portalMutation.isPending}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5 disabled:opacity-50"
        >
          Manage subscription (upgrade, downgrade, cancel)
        </button>
      </div>
    );
  }

  if (user.account_type === "coach") {
    return (
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Choose Your Plan</h2>
          <p className="text-sm text-slate-400">14 days free trial, cancel anytime.</p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {COACH_PLANS.map((plan) => (
            <div
              key={plan.key}
              className={`relative rounded-xl border p-4 ${
                plan.featured ? "border-accent bg-accent/5" : "border-white/5 bg-surface"
              }`}
            >
              {plan.featured && (
                <span className="absolute -top-2.5 left-4 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-900">
                  Popular
                </span>
              )}
              <p className="text-sm font-semibold text-white">{plan.label}</p>
              <p className="mt-1 text-xl font-bold text-white">{plan.price}</p>
              <ul className="mt-3 space-y-1 text-xs text-slate-400">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-1.5">
                    <span className="text-accent">✓</span> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => checkoutMutation.mutate(plan.key)}
                disabled={checkoutMutation.isPending}
                className="mt-4 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
              >
                Get started
              </button>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Single-Account, kein Abo.
  const remaining = Math.max(0, 2 - user.free_checkins_used);
  return (
    <div className="rounded-xl border border-white/5 bg-surface p-4">
      <h2 className="mb-1 text-lg font-semibold text-white">Your Plan</h2>
      <p className="mb-4 text-sm text-slate-400">
        <span className="font-medium text-white">{remaining}</span> of 2 free check-ins
        remaining.
      </p>
      <button
        onClick={() => checkoutMutation.mutate("single")}
        disabled={checkoutMutation.isPending}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
      >
        Continue unlimited — €4.99/month
      </button>
    </div>
  );
}

export default function Account() {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const { restart } = useOnboarding();

  const switchToCoachMutation = useMutation({
    mutationFn: api.auth.switchToCoach,
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(["auth", "me"], updatedUser);
    },
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader title="Account" />

      <ProfileSection />

      <BillingSection />

      <Card title="Need a refresher?">
        <button
          onClick={restart}
          className="rounded-lg border border-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/5"
        >
          Restart tour
        </button>
      </Card>

      {user?.account_type === "single" && (
        <Card
          title="Account type"
          description="You're currently tracking only yourself. If you also coach other clients, you can unlock a dashboard with multiple client profiles here."
        >
          <button
            onClick={() => switchToCoachMutation.mutate()}
            disabled={switchToCoachMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {switchToCoachMutation.isPending ? "Switching…" : "I also coach other clients"}
          </button>
        </Card>
      )}

      <GeminiKeySettings />
      <DisplaySettingsSection />
      <DangerZoneSection />
    </div>
  );
}
