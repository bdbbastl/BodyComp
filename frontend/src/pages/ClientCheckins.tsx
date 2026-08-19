import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import PageHeader from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { useBusyOverlay } from "../contexts/BusyOverlayContext";
import type { CheckinSubmission } from "../types";

function complianceRate(submissions: CheckinSubmission[]): string {
  const fourWeeksAgo = Date.now() - 28 * 24 * 60 * 60 * 1000;
  const recent = submissions.filter((s) => new Date(s.submitted_at).getTime() >= fourWeeksAgo);
  return `${recent.length} check-ins in the last 4 weeks`;
}

export default function ClientCheckins() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  const queryClient = useQueryClient();
  const { show, hide } = useBusyOverlay();
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<number, { text: string; videoUrl: string }>>({});
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const checkinsQuery = useQuery({
    queryKey: ["checkins", clientIdNum],
    queryFn: () => api.checkins.list(clientIdNum),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number;
      payload: { coach_feedback_text?: string; coach_feedback_video_url?: string; mark_reviewed?: boolean };
    }) => api.checkins.update(clientIdNum, id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["checkins", clientIdNum] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.checkins.delete(clientIdNum, id),
    onSuccess: () => {
      hide();
      setConfirmDeleteId(null);
      queryClient.invalidateQueries({ queryKey: ["checkins", clientIdNum] });
      // Falls die gelöschten Fotos bereits (weil reviewed) in
      // Timeline/Compare sichtbar waren, müssen die dortigen
      // Foto-Listen ebenfalls neu geladen werden.
      queryClient.invalidateQueries({ queryKey: ["photos", clientIdNum] });
    },
    onError: () => hide(),
  });

  const checkins = checkinsQuery.data ?? [];
  const draftFor = (id: number, checkin: CheckinSubmission) =>
    feedbackDrafts[id] ?? {
      text: checkin.coach_feedback_text ?? "",
      videoUrl: checkin.coach_feedback_video_url ?? "",
    };

  return (
    <div className="space-y-6">
      <PageHeader title="Check-ins" />

      {checkins.length > 0 && (
        <p className="text-sm text-slate-500">{complianceRate(checkins)}</p>
      )}

      {checkinsQuery.isLoading && <p className="text-slate-500">Loading…</p>}

      {!checkinsQuery.isLoading && checkins.length === 0 && (
        <EmptyState
          icon="📭"
          title="No submissions yet"
          description="Share the check-in link with your client so they can submit their first check-in."
        />
      )}

      <div className="space-y-3">
        {checkins.map((checkin) => {
          const isOpen = expandedId === checkin.id;
          const draft = draftFor(checkin.id, checkin);
          return (
            <div key={checkin.id} className="rounded-xl border border-white/5 bg-surface p-4">
              <button
                onClick={() => setExpandedId(isOpen ? null : checkin.id)}
                className="flex w-full items-center justify-between text-left"
              >
                <span className="text-sm text-white">
                  {new Date(checkin.submitted_at).toLocaleString("en-US")}
                  {checkin.weight_kg != null && (
                    <span className="ml-2 text-slate-500">{checkin.weight_kg} kg</span>
                  )}
                </span>
                <span
                  className={`text-xs font-medium ${
                    checkin.status === "pending" ? "text-amber-400" : "text-accent"
                  }`}
                >
                  {checkin.status === "pending" ? "⏳ Open" : "✅ Reviewed"}
                </span>
              </button>

              {isOpen && (
                <div className="mt-4 space-y-3 border-t border-white/5 pt-4">
                  {checkin.client_note && (
                    <p className="text-sm text-slate-300">&ldquo;{checkin.client_note}&rdquo;</p>
                  )}
                  {checkin.photos.length > 0 && (
                    <div className="flex gap-2 overflow-x-auto">
                      {checkin.photos.map((p) => (
                        <img
                          key={p.id}
                          src={mediaUrl(p.thumb_path)}
                          alt=""
                          className="h-20 w-20 shrink-0 rounded-lg object-cover"
                        />
                      ))}
                    </div>
                  )}
                  <label className="flex flex-col gap-1 text-sm text-slate-400">
                    Feedback
                    <textarea
                      value={draft.text}
                      onChange={(e) =>
                        setFeedbackDrafts((d) => ({
                          ...d,
                          [checkin.id]: { ...draft, text: e.target.value },
                        }))
                      }
                      rows={2}
                      className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm text-slate-400">
                    Video link (Loom, etc.)
                    <input
                      value={draft.videoUrl}
                      onChange={(e) =>
                        setFeedbackDrafts((d) => ({
                          ...d,
                          [checkin.id]: { ...draft, videoUrl: e.target.value },
                        }))
                      }
                      placeholder="https://loom.com/share/…"
                      className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-white focus:border-accent focus:outline-none"
                    />
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() =>
                        updateMutation.mutate({
                          id: checkin.id,
                          payload: {
                            coach_feedback_text: draft.text,
                            coach_feedback_video_url: draft.videoUrl,
                          },
                        })
                      }
                      disabled={updateMutation.isPending}
                      className="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/5 disabled:opacity-50"
                    >
                      Save feedback
                    </button>
                    {checkin.status === "pending" && (
                      <button
                        onClick={() =>
                          updateMutation.mutate({
                            id: checkin.id,
                            payload: {
                              coach_feedback_text: draft.text,
                              coach_feedback_video_url: draft.videoUrl,
                              mark_reviewed: true,
                            },
                          })
                        }
                        disabled={updateMutation.isPending}
                        className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
                      >
                        Mark as reviewed
                      </button>
                    )}
                  </div>
                  {confirmDeleteId === checkin.id ? (
                    <div className="space-y-2 rounded-lg border border-red-900/50 bg-red-950/20 p-3">
                      <div className="flex items-center gap-2">
                        <p className="flex-1 text-xs text-red-300">
                          Delete this check-in and its photos permanently?
                        </p>
                        <button
                          onClick={() => {
                            show("Deleting check-in…");
                            deleteMutation.mutate(checkin.id);
                          }}
                          disabled={deleteMutation.isPending}
                          className="rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
                        >
                          {deleteMutation.isPending ? "Deleting…" : "Delete"}
                        </button>
                        <button
                          onClick={() => {
                            deleteMutation.reset();
                            setConfirmDeleteId(null);
                          }}
                          className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5"
                        >
                          Cancel
                        </button>
                      </div>
                      {deleteMutation.isError && (
                        <p className="text-xs text-red-400">Delete failed - please try again.</p>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        deleteMutation.reset();
                        setConfirmDeleteId(checkin.id);
                      }}
                      className="text-xs text-red-400 hover:underline"
                    >
                      Delete check-in
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
