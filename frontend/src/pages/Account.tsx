import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { DisplaySettings } from "../api/client";
import { useCurrentUser } from "../hooks/useCurrentUser";

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
    <div className="rounded-xl border border-white/5 bg-surface p-4">
      <h2 className="mb-1 text-lg font-semibold text-white">Anzeige-Einstellungen</h2>
      <p className="mb-4 text-sm text-slate-400">
        Steuert, wie die Timeline gerendert wird - v.a. bei vielen Fotos/Tagen relevant für die
        Performance.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-slate-400">
          Bilder nebeneinander (max. {COLUMNS_MAX_LIMIT})
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
          Wochen pro Seite (max. {WEEKS_PER_PAGE_LIMIT})
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
          {saveMutation.isPending ? "Speichere…" : "Speichern"}
        </button>
      )}
    </div>
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
    <div className="rounded-xl border border-white/5 bg-surface p-4">
      <h2 className="mb-1 text-lg font-semibold text-white">KI-Einstellungen</h2>
      <p className="mb-4 text-sm text-slate-400">
        Für die KI-Judge-Analyse in Compare wird ein kostenloser Gemini-API-Key benötigt.
        Kostenlos erstellen unter{" "}
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
              Aktiv: ••••{status.last4}
              <span className="ml-1 text-slate-500">
                ({status.source === "settings" ? "eigener Key" : ".env-Fallback"})
              </span>
            </span>
          ) : (
            <span className="rounded-full bg-white/5 px-3 py-1 text-sm text-slate-500">
              Kein Key konfiguriert
            </span>
          )}
          <button
            onClick={() => setEditing(true)}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/10"
          >
            {status.configured ? "Ändern" : "Key eintragen"}
          </button>
          {status.configured && status.source === "settings" && (
            <button
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 disabled:opacity-50"
            >
              Entfernen
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
            placeholder="Gemini-API-Key"
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || saveMutation.isPending}
            className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
          >
            Speichern
          </button>
          <button
            type="button"
            onClick={() => {
              setEditing(false);
              setInputValue("");
            }}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 hover:bg-white/10"
          >
            Abbrechen
          </button>
        </form>
      )}
      {saveMutation.isError && (
        <p className="mt-2 text-xs text-red-400">Key konnte nicht gespeichert werden.</p>
      )}
    </div>
  );
}

export default function Account() {
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();

  const switchToCoachMutation = useMutation({
    mutationFn: api.auth.switchToCoach,
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(["auth", "me"], updatedUser);
    },
  });

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-xl font-semibold text-white">Account</h1>

      {user?.account_type === "single" && (
        <div className="rounded-xl border border-white/5 bg-surface p-4">
          <h2 className="mb-1 text-lg font-semibold text-white">Kontotyp</h2>
          <p className="mb-4 text-sm text-slate-400">
            Du trackst aktuell nur dich selbst. Wenn du auch andere Kunden betreust, kannst du
            hier ein Dashboard mit mehreren Kundenprofilen freischalten.
          </p>
          <button
            onClick={() => switchToCoachMutation.mutate()}
            disabled={switchToCoachMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {switchToCoachMutation.isPending ? "Wird umgestellt…" : "Ich betreue auch andere Kunden"}
          </button>
        </div>
      )}

      <GeminiKeySettings />
      <DisplaySettingsSection />
    </div>
  );
}
