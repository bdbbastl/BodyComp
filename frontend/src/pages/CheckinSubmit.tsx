import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import exifr from "exifr";
import { api, mediaUrl } from "../api/client";
import { parseWeightInput } from "../utils/weight";
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
import { formatDateWithWeek } from "../utils/date";
import { numberedPoseOptionLabel } from "../utils/poseLabel";

function isSameCalendarDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * Öffentliche, passwortlose Seite für Klienten - siehe Design-Spec
 * Abschnitt "Klienten-Ansicht". Bewusst KEIN AppShell/ClientShell: diese
 * Seite ist eigenständig, handy-tauglich und für jeden mit dem Link
 * erreichbar, unabhängig vom eingeloggten Coach-Zustand im selben Browser.
 */
export default function CheckinSubmit() {
  const { token } = useParams<{ token: string }>();
  const queryClient = useQueryClient();
  const { show, hide } = useBusyOverlay();
  const [weightKg, setWeightKg] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [photoPoses, setPhotoPoses] = useState<Record<number, number | "">>({});
  // Große, gut sichtbare Bestätigung nach erfolgreichem Absenden - bleibt
  // stehen (Formular bleibt gleichzeitig sofort wieder nutzbar), bis der
  // User sie wegklickt oder eine neue Dateiauswahl trifft.
  const [confirmation, setConfirmation] = useState<string | null>(null);

  // Object-URLs fuer die Foto-Vorschau nur einmal pro Datei-Auswahl anlegen
  // (nicht bei jedem Render, z.B. jeder Eingabe im Gewichts-/Notizfeld) und
  // beim Wechsel der Auswahl wieder freigeben, sonst leaken die Blob-URLs.
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviewUrls(urls);
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [files]);

  // Aufnahmedatum der ausgewählten Fotos (aus EXIF DateTimeOriginal, sonst
  // Datei-Änderungsdatum als Fallback - analog zum serverseitigen
  // get_taken_at() in backend/app/services/exif.py) - rein informativ für
  // die Anzeige im Header, wird nicht ans Backend mitgeschickt. Reset auf
  // [] bei jeder neuen Dateiauswahl, damit während des (schnellen, aber
  // asynchronen) EXIF-Lesens keine veralteten Daten der vorherigen
  // Auswahl angezeigt werden.
  const [photoDates, setPhotoDates] = useState<Date[]>([]);
  useEffect(() => {
    let cancelled = false;
    setPhotoDates([]);
    Promise.all(
      files.map(async (file) => {
        try {
          const exifDate = await exifr.parse(file, ["DateTimeOriginal"]);
          if (exifDate?.DateTimeOriginal instanceof Date) return exifDate.DateTimeOriginal;
        } catch {
          // Kein/kaputtes EXIF (z.B. Screenshot) - unten auf mtime zurückfallen.
        }
        return new Date(file.lastModified);
      })
    ).then((dates) => {
      if (!cancelled) setPhotoDates(dates);
    });
    return () => {
      cancelled = true;
    };
  }, [files]);

  const photoDateLabel =
    files.length === 0
      ? null
      : photoDates.length === files.length &&
          photoDates.every((d) => isSameCalendarDay(d, photoDates[0]))
        ? formatDateWithWeek(photoDates[0].toISOString())
        : photoDates.length === files.length
          ? "Mixed dates"
          : null; // EXIF-Reads noch nicht fertig - noch kein Label anzeigen

  const pageQuery = useQuery({
    queryKey: ["public-checkin", token],
    queryFn: () => api.publicCheckin.get(token!),
    enabled: !!token,
  });

  const submitMutation = useMutation({
    mutationFn: () => {
      const parsed = parseWeightInput(weightKg);
      return api.publicCheckin.submit(token!, {
        weight_kg: parsed === null || Number.isNaN(parsed) ? null : parsed,
        client_note: note.trim() === "" ? undefined : note.trim(),
        files,
        poseIds: files.map((_, i) => photoPoses[i] as number),
      });
    },
    onSuccess: () => {
      hide();
      setConfirmation(photoDateLabel ?? formatDateWithWeek(new Date().toISOString()));
      setWeightKg("");
      setNote("");
      setFiles([]);
      setPhotoPoses({});
      queryClient.invalidateQueries({ queryKey: ["public-checkin", token] });
    },
    onError: () => hide(),
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
      <div className="mx-auto max-w-2xl space-y-6">
        <div>
          <p className="text-xs text-slate-500">Check-in for</p>
          <h1 className="text-xl font-semibold text-white">{page.client_name}</h1>
          {photoDateLabel && <p className="mt-1 text-sm text-slate-400">{photoDateLabel}</p>}
        </div>

        {confirmation && (
          <div className="flex items-start gap-3 rounded-xl border border-accent/40 bg-accent/10 p-4">
            <span className="text-2xl">✅</span>
            <div className="flex-1">
              <p className="font-semibold text-white">Check-in submitted!</p>
              <p className="mt-0.5 text-sm text-slate-300">
                {confirmation} — your coach will review it soon.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setConfirmation(null)}
              aria-label="Dismiss"
              className="text-slate-400 hover:text-white"
            >
              ✕
            </button>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (
              submitMutation.isPending ||
              (files.length > 0 && files.some((_, i) => !photoPoses[i]))
            ) {
              return;
            }
            show("Submitting check-in…");
            submitMutation.mutate();
          }}
          className="space-y-4 rounded-xl border border-white/5 bg-surface p-4"
        >
          <label className="flex flex-col gap-1 text-sm text-slate-400">
            Weight (kg)
            <input
              type="text"
              inputMode="decimal"
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
              onChange={(e) => {
                setFiles(e.target.files ? Array.from(e.target.files) : []);
                setPhotoPoses({});
                setConfirmation(null);
              }}
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-900"
            />
          </label>
          {files.length > 0 && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
              {files.map((file, i) => (
                <div
                  key={`${file.name}-${i}`}
                  className="space-y-2 rounded-lg border border-white/10 bg-black/20 p-2"
                >
                  <img
                    src={previewUrls[i]}
                    alt={file.name}
                    className="h-64 w-full rounded-md bg-black/40 object-contain"
                  />
                  <select
                    required
                    aria-label={`Pose for photo ${i + 1}`}
                    value={photoPoses[i] ?? ""}
                    onChange={(e) =>
                      setPhotoPoses((prev) => ({
                        ...prev,
                        [i]: e.target.value === "" ? "" : Number(e.target.value),
                      }))
                    }
                    className="w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-white focus:border-accent focus:outline-none"
                  >
                    <option value="">Choose pose…</option>
                    {page.poses.map((pose, index) => (
                      <option key={pose.id} value={pose.id}>
                        {numberedPoseOptionLabel(index, pose.name)}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}
          {submitMutation.isError && (
            <p className="text-sm text-red-400">Submission failed - please try again.</p>
          )}
          <button
            type="submit"
            disabled={
              submitMutation.isPending ||
              (files.length > 0 && files.some((_, i) => !photoPoses[i]))
            }
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
