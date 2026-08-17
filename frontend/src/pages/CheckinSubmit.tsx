import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";

/**
 * Öffentliche, passwortlose Seite für Klienten - siehe Design-Spec
 * Abschnitt "Klienten-Ansicht". Bewusst KEIN AppShell/ClientShell: diese
 * Seite ist eigenständig, handy-tauglich und für jeden mit dem Link
 * erreichbar, unabhängig vom eingeloggten Coach-Zustand im selben Browser.
 */
export default function CheckinSubmit() {
  const { token } = useParams<{ token: string }>();
  const queryClient = useQueryClient();
  const [weightKg, setWeightKg] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  const pageQuery = useQuery({
    queryKey: ["public-checkin", token],
    queryFn: () => api.publicCheckin.get(token!),
    enabled: !!token,
  });

  const submitMutation = useMutation({
    mutationFn: () =>
      api.publicCheckin.submit(token!, {
        weight_kg: weightKg.trim() === "" ? null : Number(weightKg),
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
      }),
    onSuccess: () => {
      setWeightKg("");
      setNote("");
      setFiles([]);
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
  });

  if (pageQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4 text-slate-400">
        Loading…
      </div>
    );
  }

  if (pageQuery.isError || !pageQuery.data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <p className="text-slate-400">This link is invalid or has expired.</p>
      </div>
    );
  }

  const page = pageQuery.data;

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-slate-100">
      <div className="mx-auto max-w-md space-y-6">
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitMutation.mutate();
          }}
          className="space-y-4 rounded-xl border border-white/5 bg-surface p-4"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Weight (kg)
            <input
              type="number"
              step="0.1"
              value={weightKg}
              onChange={(e) => setWeightKg(e.target.value)}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Note (optional)
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Photos (optional)
            <input
              type="file"
              multiple
              accept="image/jpeg,image/png,image/heic,.heic"
              onChange={(e) => setFiles(e.target.files ? Array.from(e.target.files) : [])}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-900"
            />
            {files.length > 0 && (
              <span className="text-xs text-slate-500">{files.length} file(s) selected</span>
            )}
          </label>
          {submitMutation.isError && (
            <p className="text-sm text-red-400">Submission failed - please try again.</p>
          )}
          <button
            type="submit"
            disabled={submitMutation.isPending}
            className="sticky bottom-4 w-full rounded-lg bg-accent px-4 py-3 text-sm font-medium text-slate-900 shadow-lg shadow-black/40 hover:opacity-90 disabled:opacity-50 sm:static sm:py-2 sm:shadow-none"
          >
            {submitMutation.isPending ? "Submitting…" : "Submit check-in"}
          </button>
        </form>

        <div className="space-y-3">
          <h2 className="text-sm font-medium text-slate-400">My previous check-ins</h2>
          {page.submissions.length === 0 && (
            <p className="text-sm text-slate-600">No check-ins submitted yet.</p>
          )}
          {page.submissions.map((s) => (
            <div key={s.id} className="rounded-xl border border-white/5 bg-surface p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-white">
                  {new Date(s.submitted_at).toLocaleDateString("en-US")}
                </span>
                <span
                  className={`text-xs ${s.status === "reviewed" ? "text-accent" : "text-slate-500"}`}
                >
                  {s.status === "reviewed" ? "✅ Reviewed" : "⏳ Pending"}
                </span>
              </div>
              {s.weight_kg != null && (
                <p className="mt-1 text-xs text-slate-500">{s.weight_kg} kg</p>
              )}
              {s.photos.length > 0 && (
                <div className="mt-2 flex gap-2 overflow-x-auto">
                  {s.photos.map((p) => (
                    <img
                      key={p.id}
                      src={mediaUrl(p.thumb_path)}
                      alt=""
                      className="h-16 w-16 shrink-0 rounded-lg object-cover"
                    />
                  ))}
                </div>
              )}
              {s.coach_feedback_text && (
                <p className="mt-2 text-sm text-slate-300">{s.coach_feedback_text}</p>
              )}
              {s.coach_feedback_video_url && (
                <a
                  href={s.coach_feedback_video_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-sm text-accent hover:underline"
                >
                  View video feedback
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
