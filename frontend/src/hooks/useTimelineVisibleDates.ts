import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/** Liefert die Menge der Kalendertage (YYYY-MM-DD), die mindestens ein
 * Timeline-sichtbares Foto haben - dieselbe Definition wie die Timeline
 * selbst verwendet (Timeline.tsx: `api.photos.list` ist bereits
 * serverseitig auf "reviewed"/nicht-checkin-gebundene Fotos gefiltert,
 * zusätzlich clientseitig auf `pose_id != null`).
 *
 * Grund: Gewicht soll laut Live-Feedback ausschließlich zusammen mit
 * einem tatsächlich in der Timeline sichtbaren Foto-Upload zählen - wird
 * ein Check-in (und damit seine Fotos) gelöscht oder ist er noch nicht
 * vom Coach freigegeben, soll das an dem Tag hinterlegte Gewicht auch
 * nicht mehr in Gewichts-Graphen auftauchen (Statistics, SingleDashboard),
 * auch wenn der DayLog-Eintrag selbst unverändert bestehen bleibt (siehe
 * delete_checkin in backend/app/routers/checkins.py, das das Gewicht
 * bewusst NICHT löscht - das bleibt unverändert, nur die Anzeige hier
 * filtert zusätzlich). */
export function useTimelineVisibleDates(clientId: number) {
  const photosQuery = useQuery({
    queryKey: ["photos", clientId, "all"],
    queryFn: () => api.photos.list(clientId),
    enabled: !!clientId,
  });

  // useMemo hält die Set-Referenz stabil, solange sich photosQuery.data
  // nicht ändert - sonst wäre bei jedem Render ein neues Set-Objekt
  // entstanden und hätte downstream useMemo-Abhängigkeiten (z.B. in
  // Statistics.tsx) wirkungslos gemacht.
  const visibleDates = useMemo(
    () =>
      new Set(
        (photosQuery.data ?? [])
          .filter((p) => p.pose_id != null)
          .map((p) => p.taken_at.slice(0, 10))
      ),
    [photosQuery.data]
  );

  return { visibleDates, isLoading: photosQuery.isLoading, isError: photosQuery.isError };
}
