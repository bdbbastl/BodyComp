import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/PageHeader";
import { useCurrentUser } from "../hooks/useCurrentUser";

export default function Settings() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  // Bei Single-Accounts IST der "Klient" der User selbst - eine eigene
  // Klienten-E-Mail (die eh identisch zur Account-Mail wäre) und eine
  // "private Notiz über den Klienten" ergeben hier keinen Sinn (siehe
  // UX-Feedback vom 2026-08-17). Reminder-Tage bleiben relevant - das ist
  // schlicht "erinnere mich selbst". Erst als Coach mit mehreren echten
  // Klienten werden diese Felder wieder gebraucht.
  const isSingleAccount = user?.account_type === "single";
  const [newPoseName, setNewPoseName] = useState("");
  const [editing, setEditing] = useState<Record<number, string>>({});

  const [copyFeedback, setCopyFeedback] = useState(false);
  const [coachNote, setCoachNote] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [reminderDays, setReminderDays] = useState("");

  const clientQuery = useQuery({
    queryKey: ["clients", clientIdNum],
    queryFn: () => api.clients.get(clientIdNum),
  });

  useEffect(() => {
    if (!clientQuery.data) return;
    setCoachNote(clientQuery.data.coach_private_note ?? "");
    setClientEmail(clientQuery.data.email ?? "");
    setReminderDays(
      clientQuery.data.checkin_reminder_days != null ? String(clientQuery.data.checkin_reminder_days) : ""
    );
  }, [clientQuery.data]);

  const updateClientMutation = useMutation({
    mutationFn: () =>
      api.clients.update(clientIdNum, {
        // Bei Single-Accounts werden E-Mail/Notiz gar nicht angezeigt -
        // dann auch nicht mitschicken, damit ein vorhandener Wert nicht
        // versehentlich überschrieben wird (der Backend-Fallback in
        // checkin_reminders.py nutzt für Single-Accounts ohnehin
        // automatisch die Account-E-Mail, siehe services/checkin_reminders.py).
        ...(isSingleAccount
          ? {}
          : {
              coach_private_note: coachNote.trim() === "" ? null : coachNote,
              email: clientEmail.trim() === "" ? null : clientEmail.trim(),
            }),
        checkin_reminder_days: reminderDays.trim() === "" ? null : Number(reminderDays),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clients", clientIdNum] }),
  });

  const regenerateTokenMutation = useMutation({
    mutationFn: () => api.clients.regenerateCheckinToken(clientIdNum),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clients", clientIdNum] }),
  });

  const posesQuery = useQuery({
    queryKey: ["poses", clientIdNum],
    queryFn: () => api.poses.list(clientIdNum),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["poses", clientIdNum] });

  const createMutation = useMutation({
    mutationFn: (name: string) => api.poses.create(clientIdNum, name),
    onSuccess: () => {
      setNewPoseName("");
      invalidate();
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      api.poses.update(clientIdNum, id, { name }),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.poses.remove(clientIdNum, id),
    onSuccess: invalidate,
  });

  const poses = posesQuery.data ?? [];
  const MAX_POSES = 20;
  const checkinLink = clientQuery.data
    ? `${window.location.origin}/checkin/${clientQuery.data.checkin_token}`
    : "";

  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Settings" />

      <div className="space-y-4 rounded-xl border border-white/5 bg-surface p-4">
        <div data-tour="settings-checkin-link">
          <p className="text-sm font-medium text-white">Check-in link for the client</p>
          <p className="mt-1 text-xs text-slate-500">
            This link is permanently valid - the client can bookmark it and reuse it for every
            check-in.
          </p>
          <div className="mt-2 flex gap-2">
            <input
              readOnly
              value={checkinLink}
              className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-slate-300"
            />
            <button
              onClick={() => {
                navigator.clipboard.writeText(checkinLink);
                setCopyFeedback(true);
                setTimeout(() => setCopyFeedback(false), 2000);
              }}
              className="rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-white hover:bg-white/5"
            >
              {copyFeedback ? "Copied!" : "Copy"}
            </button>
          </div>
          <button
            onClick={() => {
              if (confirm("Generate a new link? The old link will stop working afterward.")) {
                regenerateTokenMutation.mutate();
              }
            }}
            disabled={regenerateTokenMutation.isPending}
            className="mt-2 text-xs text-slate-500 hover:text-white disabled:opacity-50"
          >
            Regenerate link
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateClientMutation.mutate();
          }}
          className="space-y-3 border-t border-white/5 pt-4"
        >
          {!isSingleAccount && (
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Client's email (for reminders)
              <input
                type="email"
                value={clientEmail}
                onChange={(e) => setClientEmail(e.target.value)}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            {isSingleAccount
              ? "Remind me after X days without a check-in (blank = no reminder)"
              : "Reminder after X days without a check-in (blank = no reminder)"}
            <input
              type="number"
              min={1}
              value={reminderDays}
              onChange={(e) => setReminderDays(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          {isSingleAccount && (
            <p className="text-xs text-slate-500">
              The reminder is sent to your account email ({user?.email}).
            </p>
          )}
          {!isSingleAccount && (
            <label className="flex flex-col gap-1 text-sm text-slate-400">
              Private note (visible only to you)
              <textarea
                value={coachNote}
                onChange={(e) => setCoachNote(e.target.value)}
                rows={3}
                className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
              />
            </label>
          )}
          <button
            type="submit"
            disabled={updateClientMutation.isPending}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {updateClientMutation.isPending ? "Saving…" : "Save"}
          </button>
        </form>
      </div>

      <div className="rounded-xl border border-white/5 bg-surface p-4">
        <h2 className="mb-1 text-lg font-semibold text-white">Poses</h2>
        <p className="mb-4 text-sm text-slate-400">
          The positions/angles photos are taken in (e.g. "Front", "Side", "Back") - they appear
          in this order in every photo-assignment dropdown.
        </p>
        <ul className="divide-y divide-white/5">
          {poses.map((pose, index) => {
            const editValue = editing[pose.id] ?? pose.name;
            const isDirty = editValue !== pose.name;
            return (
              <li key={pose.id} className="flex items-center gap-2 py-2">
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent"
                  title={`Position ${index + 1} - appears this way in every pose dropdown`}
                >
                  {index + 1}
                </span>
                <input
                  value={editValue}
                  onChange={(e) => setEditing((s) => ({ ...s, [pose.id]: e.target.value }))}
                  className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white focus:border-accent focus:outline-none"
                />
                {isDirty && (
                  <button
                    onClick={() =>
                      renameMutation.mutate({ id: pose.id, name: editValue.trim() })
                    }
                    disabled={!editValue.trim()}
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-40"
                  >
                    Save
                  </button>
                )}
                <button
                  onClick={() => {
                    if (confirm(`Really delete pose "${pose.name}"?`)) {
                      deleteMutation.mutate(pose.id);
                    }
                  }}
                  className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/10"
                >
                  Delete
                </button>
              </li>
            );
          })}
        </ul>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (newPoseName.trim()) createMutation.mutate(newPoseName.trim());
          }}
          className="mt-4 flex gap-2 border-t border-white/5 pt-4"
        >
          <input
            value={newPoseName}
            onChange={(e) => setNewPoseName(e.target.value)}
            placeholder="New pose, e.g. Vacuum Pose"
            disabled={poses.length >= MAX_POSES}
            className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none disabled:opacity-40"
          />
          <button
            type="submit"
            disabled={!newPoseName.trim() || poses.length >= MAX_POSES}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Add
          </button>
        </form>
        {poses.length >= MAX_POSES && (
          <p className="mt-2 text-xs text-slate-500">Maximum of {MAX_POSES} poses reached.</p>
        )}
      </div>
    </div>
  );
}
