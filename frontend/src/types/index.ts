export interface Client {
  id: number;
  name: string;
  height_cm: number | null;
  birth_date: string | null; // ISO YYYY-MM-DD
  gender: string | null;
  start_date: string | null;
  created_at: string;
  photo_count: number;
  last_activity: string | null; // ISO YYYY-MM-DD
}

export interface Pose {
  id: number;
  name: string;
  sort_order: number;
  created_at: string;
}

export interface DayLog {
  id: number;
  date: string; // ISO YYYY-MM-DD
  weight_kg: number | null;
  notes: string | null;
}

export type ProcessingStatus = "unprocessed" | "processed" | "normalization_failed";

export interface Photo {
  id: number;
  filename: string;
  original_path: string;
  preview_path: string | null;
  // Vom Backend berechnet: preview_path falls vorhanden (z.B. JPEG-
  // Vorschau für HEIC/HEIF, das Browser nicht nativ rendern können),
  // sonst original_path. Für <img>-Tags immer display_path verwenden,
  // nie original_path direkt.
  display_path: string;
  normalized_path: string | null;
  thumbnail_path: string | null;
  // Vom Backend berechnet: thumbnail_path falls vorhanden, sonst
  // display_path als Fallback. Für Grid-/Kachel-Ansichten (Timeline,
  // Import-Queue) IMMER thumb_path statt display_path verwenden - die
  // Originale sind mehrere MB große Handyfotos, das Laden Dutzender
  // davon für kleine Vorschaubilder war der Haupttreiber für lange
  // Ladezeiten. display_path bleibt für Lightbox/Compare reserviert, wo
  // die volle Auflösung gebraucht wird.
  thumb_path: string;
  taken_at: string; // ISO datetime
  status: ProcessingStatus;
  pose_id: number | null;
  day_log_id: number | null;
  width: number | null;
  height: number | null;
}

export interface UnprocessedPhoto extends Photo {
  // Vorschlag basierend auf der Reihenfolge der zuletzt zugeordneten
  // Session (siehe backend/app/services/pose_suggestion.py). null, wenn
  // keine Referenz-Session vorhanden ist oder das Foto keine passende
  // Position darin hat - dann bleibt die Auswahl leer für manuelle Wahl.
  suggested_pose_id: number | null;
}
