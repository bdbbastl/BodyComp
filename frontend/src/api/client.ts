import axios from "axios";
import type { DayLog, Photo, Pose, UnprocessedPhoto } from "../types";

export interface DisplaySettings {
  timeline_columns_max: number;
  timeline_weeks_per_page: number;
}

export type AccountType = "single" | "coach";

export interface CurrentUser {
  id: number;
  email: string;
  display_name: string;
  account_type: AccountType;
}

const client = axios.create({ baseURL: "/api", withCredentials: true });

/** Löst einen server-relativen Bildpfad (original_path/normalized_path) zur /media-URL auf. */
export function mediaUrl(relativePath: string): string {
  return `/media/${relativePath}`;
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      client.post<CurrentUser>("/auth/login", { email, password }).then((r) => r.data),
    logout: () => client.post("/auth/logout"),
    me: () => client.get<CurrentUser>("/auth/me").then((r) => r.data),
    switchToCoach: () =>
      client.post<CurrentUser>("/auth/switch-to-coach").then((r) => r.data),
  },
  poses: {
    list: () => client.get<Pose[]>("/poses").then((r) => r.data),
    create: (name: string) => client.post<Pose>("/poses", { name }).then((r) => r.data),
    update: (id: number, payload: Partial<Pick<Pose, "name" | "sort_order">>) =>
      client.patch<Pose>(`/poses/${id}`, payload).then((r) => r.data),
    remove: (id: number) => client.delete(`/poses/${id}`),
  },
  dayLogs: {
    list: () => client.get<DayLog[]>("/day-logs").then((r) => r.data),
    upsert: (payload: { date: string; weight_kg?: number | null; notes?: string | null }) =>
      client.put<DayLog>("/day-logs", payload).then((r) => r.data),
  },
  photos: {
    sync: () => client.post<Photo[]>("/photos/sync").then((r) => r.data),
    unprocessed: () => client.get<UnprocessedPhoto[]>("/photos/unprocessed").then((r) => r.data),
    list: (params?: { pose_id?: number; status?: string }) =>
      client.get<Photo[]>("/photos", { params }).then((r) => r.data),
    assign: (id: number, payload: { pose_id: number; weight_kg?: number | null }) =>
      client.post<Photo>(`/photos/${id}/assign`, payload).then((r) => r.data),
    assignBulk: (items: { photo_id: number; pose_id: number; weight_kg?: number | null }[]) =>
      client.post<Photo[]>("/photos/assign-bulk", { items }).then((r) => r.data),
    remove: (id: number) => client.delete(`/photos/${id}`),
    removeByDate: (date: string) =>
      client.delete<{ deleted: number }>(`/photos/by-date/${date}`).then((r) => r.data),
    changePose: (id: number, poseId: number) =>
      client.patch<Photo>(`/photos/${id}/pose`, { pose_id: poseId }).then((r) => r.data),
    upload: (files: File[]) => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      return client
        .post<UnprocessedPhoto[]>("/photos/upload", form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
  },
  settings: {
    getGeminiKey: () =>
      client
        .get<{ configured: boolean; source: string | null; last4: string | null }>(
          "/settings/gemini-key"
        )
        .then((r) => r.data),
    setGeminiKey: (apiKey: string) =>
      client
        .put<{ configured: boolean; source: string | null; last4: string | null }>(
          "/settings/gemini-key",
          { api_key: apiKey }
        )
        .then((r) => r.data),
    clearGeminiKey: () => client.delete("/settings/gemini-key"),
    getDisplay: () =>
      client.get<DisplaySettings>("/settings/display").then((r) => r.data),
    setDisplay: (payload: DisplaySettings) =>
      client.put<DisplaySettings>("/settings/display", payload).then((r) => r.data),
  },
  comparisons: {
    get: (params: { pose_id: number; date_x: string; date_y: string }) =>
      client
        .get<{ photo_x: Photo; photo_y: Photo }>("/comparisons", { params })
        .then((r) => r.data),
    aiAnalysis: (params: { pose_id: number; date_x: string; date_y: string }) =>
      client
        .get<{ analysis: string }>("/comparisons/ai-analysis", { params })
        .then((r) => r.data),
    aiAnalysisAll: (params: { date_x: string; date_y: string }) =>
      client
        .get<{ analysis: string }>("/comparisons/ai-analysis-all", { params })
        .then((r) => r.data),
  },
};
