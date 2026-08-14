import axios from "axios";
import type { Client, DayLog, Photo, Pose, UnprocessedPhoto } from "../types";

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
  clients: {
    list: () => client.get<Client[]>("/clients").then((r) => r.data),
    get: (clientId: number) => client.get<Client>(`/clients/${clientId}`).then((r) => r.data),
    create: (payload: {
      name: string;
      height_cm?: number | null;
      birth_date?: string | null;
      gender?: string | null;
      start_date?: string | null;
    }) => client.post<Client>("/clients", payload).then((r) => r.data),
    update: (clientId: number, payload: Partial<Omit<Client, "id" | "created_at">>) =>
      client.patch<Client>(`/clients/${clientId}`, payload).then((r) => r.data),
  },
  poses: {
    list: (clientId: number) => client.get<Pose[]>(`/clients/${clientId}/poses`).then((r) => r.data),
    create: (clientId: number, name: string) =>
      client.post<Pose>(`/clients/${clientId}/poses`, { name }).then((r) => r.data),
    update: (clientId: number, id: number, payload: Partial<Pick<Pose, "name" | "sort_order">>) =>
      client.patch<Pose>(`/clients/${clientId}/poses/${id}`, payload).then((r) => r.data),
    remove: (clientId: number, id: number) => client.delete(`/clients/${clientId}/poses/${id}`),
  },
  dayLogs: {
    list: (clientId: number) => client.get<DayLog[]>(`/clients/${clientId}/day-logs`).then((r) => r.data),
    upsert: (clientId: number, payload: { date: string; weight_kg?: number | null; notes?: string | null }) =>
      client.put<DayLog>(`/clients/${clientId}/day-logs`, payload).then((r) => r.data),
  },
  photos: {
    sync: (clientId: number) => client.post<Photo[]>(`/clients/${clientId}/photos/sync`).then((r) => r.data),
    unprocessed: (clientId: number) =>
      client.get<UnprocessedPhoto[]>(`/clients/${clientId}/photos/unprocessed`).then((r) => r.data),
    list: (clientId: number, params?: { pose_id?: number; status?: string }) =>
      client.get<Photo[]>(`/clients/${clientId}/photos`, { params }).then((r) => r.data),
    assign: (clientId: number, id: number, payload: { pose_id: number; weight_kg?: number | null }) =>
      client.post<Photo>(`/clients/${clientId}/photos/${id}/assign`, payload).then((r) => r.data),
    assignBulk: (clientId: number, items: { photo_id: number; pose_id: number; weight_kg?: number | null }[]) =>
      client.post<Photo[]>(`/clients/${clientId}/photos/assign-bulk`, { items }).then((r) => r.data),
    remove: (clientId: number, id: number) => client.delete(`/clients/${clientId}/photos/${id}`),
    removeByDate: (clientId: number, date: string) =>
      client.delete<{ deleted: number }>(`/clients/${clientId}/photos/by-date/${date}`).then((r) => r.data),
    changePose: (clientId: number, id: number, poseId: number) =>
      client.patch<Photo>(`/clients/${clientId}/photos/${id}/pose`, { pose_id: poseId }).then((r) => r.data),
    upload: (clientId: number, files: File[]) => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      return client
        .post<UnprocessedPhoto[]>(`/clients/${clientId}/photos/upload`, form, {
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
    get: (clientId: number, params: { pose_id: number; date_x: string; date_y: string }) =>
      client
        .get<{ photo_x: Photo; photo_y: Photo }>(`/clients/${clientId}/comparisons`, { params })
        .then((r) => r.data),
    aiAnalysis: (clientId: number, params: { pose_id: number; date_x: string; date_y: string }) =>
      client
        .get<{ analysis: string }>(`/clients/${clientId}/comparisons/ai-analysis`, { params })
        .then((r) => r.data),
    aiAnalysisAll: (clientId: number, params: { date_x: string; date_y: string }) =>
      client
        .get<{ analysis: string }>(`/clients/${clientId}/comparisons/ai-analysis-all`, { params })
        .then((r) => r.data),
  },
};
