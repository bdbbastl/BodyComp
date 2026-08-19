import axios from "axios";
import type { CheckinSubmission, Client, CoachDashboardSummary, DayLog, NeedsAttentionClient, Photo, Pose, PendingCheckinSummary, PublicCheckinPage, UnprocessedPhoto, WeekStats } from "../types";

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
  created_at: string;
  // false bei Google-only-Accounts (kein eigenes Passwort gesetzt) -
  // steuert z.B. ob bei der Konto-Löschung ein Passwortfeld angezeigt wird.
  has_password: boolean;
  // true bei Accounts, die sich über Google einloggen - steuert, ob der
  // E-Mail-Änderungsbereich in Account.tsx angezeigt wird.
  has_google_account: boolean;
  subscription_status: string | null;
  subscription_tier: string | null;
  trial_ends_at: string | null;
  free_checkins_used: number;
  onboarding_completed_at: string | null;
}

const client = axios.create({ baseURL: "/api", withCredentials: true });

/** Löst einen server-relativen Bildpfad (original_path/normalized_path) zur /media-URL auf. */
export function mediaUrl(relativePath: string): string {
  return `/media/${relativePath}`;
}

export const api = {
  dashboard: {
    coachSummary: () =>
      client.get<CoachDashboardSummary>("/dashboard/coach-summary").then((r) => r.data),
  },
  billing: {
    checkout: (tier: "starter" | "pro" | "business" | "single") =>
      client.post<{ checkout_url: string }>("/billing/checkout", { tier }).then((r) => r.data),
    portal: () => client.post<{ portal_url: string }>("/billing/portal").then((r) => r.data),
  },
  auth: {
    login: (email: string, password: string) =>
      client.post<CurrentUser>("/auth/login", { email, password }).then((r) => r.data),
    logout: () => client.post("/auth/logout"),
    me: () => client.get<CurrentUser>("/auth/me").then((r) => r.data),
    switchToCoach: () =>
      client.post<CurrentUser>("/auth/switch-to-coach").then((r) => r.data),
    completeOnboarding: () =>
      client.patch<CurrentUser>("/auth/onboarding-complete").then((r) => r.data),
    signup: (payload: { email: string; password: string; display_name: string; privacy_accepted: boolean }) =>
      client.post<CurrentUser>("/auth/signup", payload).then((r) => r.data),
    verifyEmail: (token: string) =>
      client.get("/auth/verify-email", { params: { token } }).then((r) => r.data),
    resendVerification: (email: string) => client.post("/auth/resend-verification", { email }),
    forgotPassword: (email: string) => client.post("/auth/forgot-password", { email }),
    resetPassword: (token: string, new_password: string) =>
      client.post("/auth/reset-password", { token, new_password }),
    deleteAccount: (password?: string) =>
      client.delete("/auth/me", { data: { password } }),
    changePassword: (currentPassword: string, newPassword: string) =>
      client.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    changeEmail: (newEmail: string, currentPassword: string) =>
      client.post("/auth/change-email", {
        new_email: newEmail,
        current_password: currentPassword,
      }),
    confirmEmailChange: (token: string) =>
      client
        .get<{ changed: boolean; new_email: string }>("/auth/confirm-email-change", {
          params: { token },
        })
        .then((r) => r.data),
    exportData: () => client.get("/auth/me/export").then((r) => r.data),
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
    update: (
      clientId: number,
      payload: Partial<Omit<Client, "id" | "created_at" | "checkin_token" | "photo_count" | "last_activity" | "pending_checkins_count">>
    ) => client.patch<Client>(`/clients/${clientId}`, payload).then((r) => r.data),
    regenerateCheckinToken: (clientId: number) =>
      client.post<Client>(`/clients/${clientId}/checkin-token/regenerate`).then((r) => r.data),
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
    upload: (clientId: number, files: File[], onUploadProgress?: (percent: number) => void) => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      return client
        .post<UnprocessedPhoto[]>(`/clients/${clientId}/photos/upload`, form, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: onUploadProgress
            ? (e) => {
                if (e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100));
              }
            : undefined,
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
  checkins: {
    list: (clientId: number) =>
      client.get<CheckinSubmission[]>(`/clients/${clientId}/checkins`).then((r) => r.data),
    update: (
      clientId: number,
      checkinId: number,
      payload: { coach_feedback_text?: string; coach_feedback_video_url?: string; mark_reviewed?: boolean }
    ) =>
      client
        .patch<CheckinSubmission>(`/clients/${clientId}/checkins/${checkinId}`, payload)
        .then((r) => r.data),
  },
  publicCheckin: {
    get: (token: string) =>
      client.get<PublicCheckinPage>(`/public/checkin/${token}`).then((r) => r.data),
    submit: (token: string, payload: { weight_kg?: number | null; client_note?: string; files: File[] }) => {
      const form = new FormData();
      if (payload.weight_kg != null) form.append("weight_kg", String(payload.weight_kg));
      if (payload.client_note) form.append("client_note", payload.client_note);
      for (const file of payload.files) form.append("files", file);
      return client
        .post<CheckinSubmission>(`/public/checkin/${token}/submit`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data);
    },
  },
};
