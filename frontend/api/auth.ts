import type { Shareholder } from "../types";
import { apiRequest, jsonRequest } from "./client";

export interface AuthCheckResult {
  authenticated: boolean;
  shareholder?: Shareholder | null;
}

export interface LoginResult {
  message: string;
  shareholder: Shareholder;
}

export const authApi = {
  check: (signal?: AbortSignal) =>
    apiRequest<AuthCheckResult>("/api/auth/check", { signal }),
  login: (email: string, password: string) =>
    apiRequest<LoginResult>("/api/auth/login", jsonRequest("POST", { email, password })),
  sendMagicLink: (email: string) =>
    apiRequest<{ message: string }>("/api/auth/magic-link", jsonRequest("POST", { email })),
  verifyMagicLink: (token: string, signal?: AbortSignal) =>
    apiRequest<LoginResult>("/api/auth/magic-link/verify", {
      ...jsonRequest("POST", { token }),
      signal,
    }),
  logout: () => apiRequest<{ message: string }>("/api/auth/logout", { method: "POST" }),
  markTourSeen: () => apiRequest<{ ok: boolean }>("/api/auth/tour-seen", { method: "POST" }),
  updateNotificationPreferences: (enabled: boolean) =>
    apiRequest<Shareholder>(
      "/api/notification-preferences",
      jsonRequest("PUT", { cancellation_availability_emails_enabled: enabled }),
    ),
  validateCancellationAvailabilityUnsubscribe: (token: string, signal?: AbortSignal) =>
    apiRequest<{ valid: boolean; subscribed: boolean; email: string | null }>(
      `/api/notification-preferences/cancellation-availability/unsubscribe?token=${encodeURIComponent(token)}`,
      { signal },
    ),
  unsubscribeCancellationAvailability: (token: string) =>
    apiRequest<{ unsubscribed: boolean; email: string; message: string }>(
      "/api/notification-preferences/cancellation-availability/unsubscribe",
      jsonRequest("POST", { token }),
    ),
};
