import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, mediaUrl } from "../api/client";
import type { Photo, Pose } from "../types";
import { formatDateWithWeek } from "../utils/date";
import { transformStyle, usePanZoom } from "../hooks/usePanZoom";
import { ZoomSlider } from "../components/ZoomSlider";
import { numberedPoseOptionLabel } from "../utils/poseLabel";
import PageHeader from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { SkeletonCard } from "../components/Skeleton";

const DEFAULT_COLUMNS_MAX = 5;
const DEFAULT_WEEKS_PER_PAGE = 8;

/** Anzahl Spalten = direkt die vom User in den Settings konfigurierte
 * "Bilder nebeneinander"-Zahl (1-10, siehe Settings.tsx "Anzeige") - außer
 * es gibt weniger Fotos als die Einstellung, dann natürlich nur so viele
 * Spalten wie Fotos vorhanden sind. Bei z.B. 7 eingestellt und 7 Fotos
 * stehen alle 7 nebeneinander; bei mehr Fotos als die Einstellung wird
 * per normalem CSS-Grid-Umbruch in die nächste Zeile gewrappt (bewusst
 * keine "balancierte" Sonderlogik mehr - der User will die Spaltenzahl
 * direkt und 1:1 steuern können). */
function balancedColumns(count: number, maxCols: number): number {
  return Math.min(count || 1, maxCols);
}

interface DayGroup {
  date: string;
  weight_kg: number | null;
  photos: Photo[];
}

export default function Timeline() {
  const { clientId } = useParams<{ clientId: string }>();
  const clientIdNum = Number(clientId);
  // Kein status-Filter: Fotos gelten als "zugeordnet" sobald pose_id gesetzt
  // ist, unabhängig davon ob die MediaPipe-Normalisierung geklappt hat
  // (normalization_failed-Fotos gehören trotzdem in die Timeline, nur der
  // Overlay-Vergleich ist für sie nicht verfügbar).
  const photosQuery = useQuery({
    queryKey: ["photos", clientIdNum, "all"],
    queryFn: () => api.photos.list(clientIdNum),
    select: (photos) => photos.filter((p) => p.pose_id != null),
  });
  const dayLogsQuery = useQuery({
    queryKey: ["day-logs", clientIdNum],
    queryFn: () => api.dayLogs.list(clientIdNum),
  });
  const posesQuery = useQuery({
    queryKey: ["poses", clientIdNum],
    queryFn: () => api.poses.list(clientIdNum),
  });
  const displaySettingsQuery = useQuery({
    queryKey: ["settings", "display"],
    queryFn: api.settings.getDisplay,
  });

  if (photosQuery.isLoading || dayLogsQuery.isLoading || posesQuery.isLoading || displaySettingsQuery.isLoading) {
    return (
      <>
        <PageHeader title="Timeline" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
          {Array.from({ length: 10 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </>
    );
  }
  if (photosQuery.isError || dayLogsQuery.isError || posesQuery.isError) {
    return (
      <>
        <PageHeader title="Timeline" />
        <p className="text-red-400">Timeline konnte nicht geladen werden.</p>
      </>
    );
  }

  const columnsMax = displaySettingsQuery.data?.timeline_columns_max ?? DEFAULT_COLUMNS_MAX;
  const weeksPerPage = displaySettingsQuery.data?.timeline_weeks_per_page ?? DEFAULT_WEEKS_PER_PAGE;

  const photos = photosQuery.data ?? [];
  const weightByDate = new Map(
    (dayLogsQuery.data ?? []).map((d) => [d.date, d.weight_kg])
  );
  // api.poses.list() liefert bereits nach sort_order sortiert (siehe
  // backend/app/routers/poses.py) - das ist exakt die in den Settings
  // konfigurierte Reihenfolge. poseOrderById übersetzt das in einen
  // Sortier-Index, damit die Fotos pro Tag in derselben Reihenfolge
  // erscheinen wie die Posen in den Settings, statt in Zuordnungs-/
  // Insert-Reihenfolge.
  const poses = posesQuery.data ?? [];
  const poseNameById = new Map(poses.map((p) => [p.id, p.name]));
  const poseOrderById = new Map(poses.map((p, index) => [p.id, index]));

  const groups = new Map<string, DayGroup>();
  for (const photo of photos) {
    const date = photo.taken_at.slice(0, 10);
    if (!groups.has(date)) {
      groups.set(date, { date, weight_kg: weightByDate.get(date) ?? null, photos: [] });
    }
    groups.get(date)!.photos.push(photo);
  }
  for (const group of groups.values()) {
    group.photos.sort(
      (a, b) =>
        (poseOrderById.get(a.pose_id ?? -1) ?? Number.MAX_SAFE_INTEGER) -
        (poseOrderById.get(b.pose_id ?? -1) ?? Number.MAX_SAFE_INTEGER)
    );
  }
  const sortedGroups = [...groups.values()].sort((a, b) => (a.date < b.date ? 1 : -1));

  if (sortedGroups.length === 0) {
    return (
      <>
        <PageHeader title="Timeline" />
        <EmptyState
          icon="📸"
          title="Hier ist noch nichts zu sehen"
          description="Sobald der erste Check-in oder Foto-Import da ist, taucht er hier auf."
          action={
            <Link
              to={`/clients/${clientIdNum}/unprocessed`}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-slate-900 hover:opacity-90"
            >
              Zu Import
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Timeline" />
      <TimelineWithLightbox
        clientId={clientIdNum}
        sortedGroups={sortedGroups}
        poses={poses}
        poseNameById={poseNameById}
        columnsMax={columnsMax}
        weeksPerPage={weeksPerPage}
      />
    </>
  );
}

/** Eigene Komponente für Lightbox- und Paginierungs-State, damit diese
 * nicht die frühen Returns oben (Lade-/Fehler-/Leerzustand) durchqueren
 * müssen. Paginiert client-seitig über die schon geladenen Gruppen -
 * spart hier zwar keine Netzwerk-Requests, aber den DOM-/Render-Aufwand
 * für sehr viele Tage gleichzeitig (das eigentliche Performance-Ziel laut
 * Anforderung). */
function TimelineWithLightbox({
  clientId,
  sortedGroups,
  poses,
  poseNameById,
  columnsMax,
  weeksPerPage,
}: {
  clientId: number;
  sortedGroups: DayGroup[];
  poses: Pose[];
  poseNameById: Map<number, string>;
  columnsMax: number;
  weeksPerPage: number;
}) {
  const [lightboxPhoto, setLightboxPhoto] = useState<Photo | null>(null);
  const [page, setPage] = useState(0);

  const pageCount = Math.max(1, Math.ceil(sortedGroups.length / weeksPerPage));
  const clampedPage = Math.min(page, pageCount - 1);
  const pageGroups = sortedGroups.slice(
    clampedPage * weeksPerPage,
    clampedPage * weeksPerPage + weeksPerPage
  );

  return (
    <div className="space-y-8">
      {pageCount > 1 && (
        <TimelinePagination page={clampedPage} pageCount={pageCount} onPageChange={setPage} />
      )}
      {pageGroups.map((group) => (
        <DayGroupSection
          key={group.date}
          clientId={clientId}
          group={group}
          poses={poses}
          poseNameById={poseNameById}
          onOpenPhoto={setLightboxPhoto}
          columnsMax={columnsMax}
        />
      ))}
      {pageCount > 1 && (
        <TimelinePagination page={clampedPage} pageCount={pageCount} onPageChange={setPage} />
      )}
      {lightboxPhoto && (
        <Lightbox
          photo={lightboxPhoto}
          label={
            lightboxPhoto.pose_id ? poseNameById.get(lightboxPhoto.pose_id) ?? "Foto" : "Foto"
          }
          onClose={() => setLightboxPhoto(null)}
        />
      )}
    </div>
  );
}

function TimelinePagination({
  page,
  pageCount,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-center gap-3 text-sm">
      <button
        onClick={() => onPageChange(Math.max(0, page - 1))}
        disabled={page === 0}
        className="rounded-full bg-surface px-3 py-1.5 text-slate-300 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-30"
      >
        ‹ Neuer
      </button>
      <span className="text-slate-400">
        Seite {page + 1} von {pageCount}
      </span>
      <button
        onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}
        disabled={page === pageCount - 1}
        className="rounded-full bg-surface px-3 py-1.5 text-slate-300 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-30"
      >
        Älter ›
      </button>
    </div>
  );
}

function DayGroupSection({
  clientId,
  group,
  poses,
  poseNameById,
  onOpenPhoto,
  columnsMax,
}: {
  clientId: number;
  group: DayGroup;
  poses: Pose[];
  poseNameById: Map<number, string>;
  onOpenPhoto: (photo: Photo) => void;
  columnsMax: number;
}) {
  const queryClient = useQueryClient();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // Ein-/ausklappbar zum Platz sparen (v.a. bei vielen Tagen auf einer
  // Seite) - bewusst nicht persistiert, jede Seite startet aufgeklappt.
  const [collapsed, setCollapsed] = useState(false);

  const deleteDayMutation = useMutation({
    mutationFn: () => api.photos.removeByDate(clientId, group.date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["photos", clientId] });
      setConfirmingDelete(false);
    },
  });

  const cols = balancedColumns(group.photos.length, columnsMax);

  return (
    <section className="rounded-xl border border-white/5 bg-surface p-4 sm:p-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Aufklappen" : "Einklappen"}
            title={collapsed ? "Aufklappen" : "Einklappen"}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/5 text-xs text-slate-400 transition-transform hover:bg-white/10"
            style={{ transform: collapsed ? "rotate(-90deg)" : undefined }}
          >
            ▾
          </button>
          <h2 className="text-lg font-semibold text-white">{formatDateWithWeek(group.date)}</h2>
        </div>
        <div className="flex items-center gap-2">
          <WeightEditor clientId={clientId} date={group.date} weightKg={group.weight_kg} />
          {confirmingDelete ? (
            <span className="flex items-center gap-1 text-xs">
              <span className="text-slate-400">Alle {group.photos.length} Fotos löschen?</span>
              <button
                onClick={() => deleteDayMutation.mutate()}
                disabled={deleteDayMutation.isPending}
                className="rounded-full bg-red-500/80 px-2 py-1 font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                Ja, löschen
              </button>
              <button
                onClick={() => setConfirmingDelete(false)}
                className="rounded-full border border-white/10 px-2 py-1 text-slate-400 hover:bg-white/10"
              >
                Abbrechen
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmingDelete(true)}
              className="rounded-full bg-white/5 px-3 py-1 text-sm text-red-400 transition-colors hover:bg-white/10"
              title="Alle Fotos dieses Tages löschen"
            >
              Tag löschen
            </button>
          )}
        </div>
      </div>
      {!collapsed && (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        >
          {group.photos.map((photo) => (
            <PhotoCard
              key={photo.id}
              clientId={clientId}
              photo={photo}
              poses={poses}
              poseNameById={poseNameById}
              onOpen={onOpenPhoto}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function PhotoCard({
  clientId,
  photo,
  poses,
  poseNameById,
  onOpen,
}: {
  clientId: number;
  photo: Photo;
  poses: Pose[];
  poseNameById: Map<number, string>;
  onOpen: (photo: Photo) => void;
}) {
  const queryClient = useQueryClient();
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => api.photos.remove(clientId, photo.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["photos", clientId] }),
  });

  const changePoseMutation = useMutation({
    mutationFn: (poseId: number) => api.photos.changePose(clientId, photo.id, poseId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["photos", clientId] }),
  });

  return (
    <figure className="overflow-hidden rounded-lg border border-white/5 bg-black/20">
      <div className="relative">
        <img
          src={mediaUrl(photo.thumb_path)}
          alt={photo.pose_id ? poseNameById.get(photo.pose_id) ?? "Foto" : "Foto"}
          className="aspect-[3/4] w-full cursor-zoom-in object-cover"
          loading="lazy"
          onClick={() => !confirmingDelete && onOpen(photo)}
        />
        {confirmingDelete ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/80 p-1 text-center">
            <span className="text-xs text-slate-200">Foto löschen?</span>
            <div className="flex gap-1">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="rounded-full bg-red-500/80 px-2 py-0.5 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                Ja
              </button>
              <button
                onClick={() => setConfirmingDelete(false)}
                className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-slate-300 hover:bg-white/10"
              >
                Nein
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setConfirmingDelete(true)}
            title="Foto löschen"
            className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-sm text-red-400 hover:bg-black/80"
          >
            ✕
          </button>
        )}
      </div>
      <figcaption className="px-1.5 py-1.5">
        <select
          value={photo.pose_id ?? ""}
          onChange={(e) => changePoseMutation.mutate(Number(e.target.value))}
          disabled={changePoseMutation.isPending}
          className="w-full rounded border border-white/10 bg-black/30 px-1 py-0.5 text-xs text-slate-300 focus:border-accent focus:outline-none"
        >
          {poses.map((pose, index) => (
            <option key={pose.id} value={pose.id}>
              {numberedPoseOptionLabel(index, pose.name)}
            </option>
          ))}
        </select>
      </figcaption>
    </figure>
  );
}

/** Klick auf das Gewicht (oder "Gewicht eintragen", falls noch keins
 * erfasst ist) blendet ein Eingabefeld ein - so lässt sich das
 * Körpergewicht auch nachträglich pro Tag eintragen/korrigieren. */
function WeightEditor({
  clientId,
  date,
  weightKg,
}: {
  clientId: number;
  date: string;
  weightKg: number | null;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(weightKg != null ? String(weightKg) : "");

  useEffect(() => {
    setValue(weightKg != null ? String(weightKg) : "");
  }, [weightKg]);

  const mutation = useMutation({
    mutationFn: () =>
      api.dayLogs.upsert(clientId, { date, weight_kg: value.trim() === "" ? null : Number(value) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["day-logs", clientId] });
      setEditing(false);
    },
  });

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="rounded-full bg-white/5 px-3 py-1 text-sm text-accent transition-colors hover:bg-white/10"
        title="Gewicht bearbeiten"
      >
        {weightKg != null ? `${weightKg.toFixed(1)} kg` : "Gewicht eintragen"}
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="flex items-center gap-1"
    >
      <input
        type="number"
        step="0.1"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="kg"
        className="w-20 rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none"
      />
      <button
        type="submit"
        disabled={mutation.isPending}
        className="rounded-lg bg-accent px-2 py-1 text-xs font-medium text-slate-900 hover:opacity-90 disabled:opacity-50"
      >
        ✓
      </button>
      <button
        type="button"
        onClick={() => {
          setEditing(false);
          setValue(weightKg != null ? String(weightKg) : "");
        }}
        className="rounded-lg border border-white/10 px-2 py-1 text-xs text-slate-400 hover:bg-white/10"
      >
        ✕
      </button>
    </form>
  );
}

/** Vollbild-Layer für ein einzelnes Timeline-Foto: Mausrad zum Zoomen, bei
 * Zoom Klick+Ziehen zum Verschieben (siehe usePanZoom), Escape/Backdrop-
 * Klick/× schließt. Nutzt dieselbe Pan/Zoom-Logik wie Compare. */
function Lightbox({ photo, label, onClose }: { photo: Photo; label: string; onClose: () => void }) {
  const { scale, translate, containerRef, isDragging, reset, setScaleFromSlider } = usePanZoom();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/90 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <button
        onClick={onClose}
        aria-label="Schließen"
        className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-xl text-white hover:bg-white/20"
      >
        ✕
      </button>
      <div
        ref={containerRef}
        className="relative max-h-[80vh] w-full max-w-xl overflow-hidden rounded-xl bg-black"
        style={{ aspectRatio: "3 / 4", cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "zoom-in" }}
        onDoubleClick={reset}
        title="Mausrad zum Zoomen, bei Zoom Klick+Ziehen zum Verschieben, Doppelklick zum Zurücksetzen"
      >
        <img
          src={mediaUrl(photo.display_path)}
          alt={label}
          draggable={false}
          className="h-full w-full object-contain"
          style={transformStyle(translate, scale)}
        />
        {scale > 1 && (
          <span className="pointer-events-none absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-slate-200">
            {scale.toFixed(1)}×
          </span>
        )}
      </div>
      <p className="text-sm text-slate-300">{label}</p>
      <div className="w-full max-w-xl rounded-xl border border-white/5 bg-surface p-4">
        <ZoomSlider scale={scale} onChange={setScaleFromSlider} />
      </div>
    </div>
  );
}
