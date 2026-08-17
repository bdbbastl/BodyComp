import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import type { UnprocessedPhoto } from "../types";
import { formatDateWithWeek } from "../utils/date";
import { parseWeightInput } from "../utils/weight";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import PageHeader from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";

interface DateGroup {
  date: string; // YYYY-MM-DD
  photos: UnprocessedPhoto[];
}

export default function Unprocessed() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const queryClient = useQueryClient();
  const [selectedPoseId, setSelectedPoseId] = useState<Record<number, number | "">>({});
  // Ein Gewicht pro Tag statt pro Foto - gilt für alle Fotos dieses
  // Datums, wie gewünscht ("für alle Bilder eines Tages").
  const [weightByDate, setWeightByDate] = useState<Record<string, string>>({});

  const posesQuery = useQuery({
    queryKey: ["poses", clientIdNum],
    queryFn: () => api.poses.list(clientIdNum),
  });
  const photosQuery = useQuery({
    queryKey: ["photos", clientIdNum, "unprocessed"],
    queryFn: () => api.photos.unprocessed(clientIdNum),
  });

  // Neue Fotos mit ihrem Pose-Vorschlag vorbelegen (siehe backend
  // services/pose_suggestion.py). Nur für Fotos, die noch keinen Eintrag
  // in selectedPoseId haben - überschreibt also nie eine bereits
  // getroffene (manuelle oder vorbelegte) Auswahl bei einem Refetch.
  useEffect(() => {
    if (!photosQuery.data) return;
    setSelectedPoseId((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const photo of photosQuery.data) {
        if (!(photo.id in next) && photo.suggested_pose_id != null) {
          next[photo.id] = photo.suggested_pose_id;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [photosQuery.data]);

  // Datei-Upload: Dateien werden nach photos_incoming/ kopiert und im
  // selben Request direkt verarbeitet (Backend ruft intern denselben Scan
  // wie /sync auf) - kein separater "Ordner synchronisieren"-Klick nötig
  // für hochgeladene Dateien.
  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => api.photos.upload(clientIdNum, files),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] }),
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const assignMutation = useMutation({
    mutationFn: ({ id, poseId, weight }: { id: number; poseId: number; weight: string }) => {
      const parsed = parseWeightInput(weight);
      return api.photos.assign(clientIdNum, id, {
        pose_id: poseId,
        weight_kg: parsed === null || Number.isNaN(parsed) ? null : parsed,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
      queryClient.invalidateQueries({ queryKey: ["day-logs", clientIdNum] });
    },
  });

  const bulkAssignMutation = useMutation({
    mutationFn: (items: { photo_id: number; pose_id: number; weight_kg: number | null }[]) =>
      api.photos.assignBulk(clientIdNum, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
      queryClient.invalidateQueries({ queryKey: ["day-logs", clientIdNum] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.photos.remove(clientIdNum, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] }),
  });

  const poses = posesQuery.data ?? [];
  const photos = photosQuery.data ?? [];

  const groups: DateGroup[] = Object.values(
    photos.reduce<Record<string, DateGroup>>((acc, photo) => {
      const date = photo.taken_at.slice(0, 10);
      (acc[date] ??= { date, photos: [] }).photos.push(photo);
      return acc;
    }, {})
  ).sort((a, b) => (a.date < b.date ? 1 : -1)); // neueste Session zuerst

  // Nur Fotos mit gesetzter Pose werden mitgeschickt - alle anderen
  // (leeres Dropdown, keine passende Vorschlags-Position) bleiben
  // unverändert in der Queue für die manuelle Einzelzuordnung.
  const readyToBulkAssign = photos.filter((p) => selectedPoseId[p.id]);

  function weightForDate(date: string): number | null {
    const raw = weightByDate[date] ?? "";
    const parsed = parseWeightInput(raw);
    return parsed === null || Number.isNaN(parsed) ? null : parsed;
  }

  function handleBulkAssign() {
    const items = readyToBulkAssign.map((photo) => ({
      photo_id: photo.id,
      pose_id: Number(selectedPoseId[photo.id]),
      weight_kg: weightForDate(photo.taken_at.slice(0, 10)),
    }));
    bulkAssignMutation.mutate(items);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Import"
        actions={
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/jpeg,image/png,image/heic,.heic"
              className="hidden"
              onChange={(e) => {
                const files = e.target.files ? Array.from(e.target.files) : [];
                if (files.length > 0) uploadMutation.mutate(files);
                e.target.value = ""; // erlaubt erneuten Upload derselben Datei(en)
              }}
            />
            <button
              data-tour="unprocessed-upload"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploadMutation.isPending ? "Uploading…" : "📤 Upload photos"}
            </button>
            <button
              onClick={handleBulkAssign}
              disabled={readyToBulkAssign.length === 0 || bulkAssignMutation.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              title={
                readyToBulkAssign.length === 0
                  ? "No photos with a pose set"
                  : `Assign ${readyToBulkAssign.length} photo(s)`
              }
            >
              {bulkAssignMutation.isPending
                ? "Assigning…"
                : `Save all assigned (${readyToBulkAssign.length})`}
            </button>
          </div>
        }
      />

      {uploadMutation.isError && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">
          Upload failed. Please try again.
        </p>
      )}

      {(bulkAssignMutation.error as any)?.response?.status === 402 && (
        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">
          Free allowance used up -{" "}
          <Link to="/account" className="underline">
            Subscribe
          </Link>
          {" "}to submit more check-ins.
        </p>
      )}

      {photosQuery.isLoading && <p className="text-slate-500">Loading…</p>}

      {!photosQuery.isLoading && photos.length === 0 && (
        <EmptyState
          icon="✨"
          title="All sorted!"
          description={'No unprocessed photos left. Click "Upload photos" for new images.'}
          action={
            <button
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              📤 Upload photos
            </button>
          }
        />
      )}

      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.date} className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 pb-2">
              <h2 className="text-base font-semibold text-white">
                {formatDateWithWeek(group.date)}
                <span className="ml-2 text-sm font-normal text-slate-500">
                ({group.photos.length} photo{group.photos.length === 1 ? "" : "s"})
                </span>
              </h2>
              <label className="flex items-center gap-2 text-sm text-slate-400">
                Body weight for this day
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="kg, optional"
                  value={weightByDate[group.date] ?? ""}
                  onChange={(e) =>
                    setWeightByDate((s) => ({ ...s, [group.date]: e.target.value }))
                  }
                  className="w-32 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none"
                />
              </label>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.photos.map((photo) => {
                const pose = selectedPoseId[photo.id] ?? "";
                const isAssigning =
                  assignMutation.isPending && assignMutation.variables?.id === photo.id;
                const isSuggested =
                  photo.suggested_pose_id != null && pose === photo.suggested_pose_id;

                const isDeleting = deleteMutation.isPending && deleteMutation.variables === photo.id;

                return (
                  <div
                    key={photo.id}
                    className="overflow-hidden rounded-xl border border-white/5 bg-surface"
                  >
                    <div className="relative">
                      <img
                        src={mediaUrl(photo.thumb_path)}
                        alt={photo.filename}
                        className="aspect-[3/4] w-full object-cover"
                      />
                      <button
                        onClick={() => {
                          if (confirm(`Really delete "${photo.filename}"?`)) {
                            deleteMutation.mutate(photo.id);
                          }
                        }}
                        disabled={isDeleting}
                        title="Delete photo"
                        aria-label="Delete photo"
                        className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white/80 backdrop-blur transition-colors hover:bg-red-500/80 hover:text-white disabled:opacity-50"
                      >
                        {isDeleting ? "…" : "✕"}
                      </button>
                    </div>
                    <div className="space-y-2 p-3">
                      <p className="truncate text-xs text-slate-500">
                        {photo.filename} ·{" "}
                        {new Date(photo.taken_at).toLocaleTimeString("en-US")}
                      </p>
                      <div className="flex items-center gap-2">
                        <select
                          value={pose}
                          onChange={(e) =>
                            setSelectedPoseId((s) => ({
                              ...s,
                              [photo.id]: e.target.value ? Number(e.target.value) : "",
                            }))
                          }
                          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-accent focus:outline-none"
                        >
                          <option value="">Choose pose…</option>
                          {poses.map((p, index) => (
                            <option key={p.id} value={p.id}>
                              {numberedPoseOptionLabel(index, p.name)}
                            </option>
                          ))}
                        </select>
                        {isSuggested && (
                          <span
                            title="Suggestion based on last session"
                            className="shrink-0 rounded-full bg-accent/20 px-2 py-1 text-xs text-accent"
                          >
                            Suggested
                          </span>
                        )}
                      </div>
                      <button
                        disabled={!pose || isAssigning}
                        onClick={() =>
                          assignMutation.mutate({
                            id: photo.id,
                            poseId: Number(pose),
                            weight: weightByDate[group.date] ?? "",
                          })
                        }
                        className="w-full rounded-lg border border-white/10 bg-black/30 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {isAssigning ? "Assigning…" : "Assign individually"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
