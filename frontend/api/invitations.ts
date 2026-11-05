import { apiRequest, jsonRequest } from "./client";

export interface InvitationTokenInfo {
  valid: boolean;
  email?: string;
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  share_name?: string;
  is_viewer?: boolean;
}

export interface AvailableInvitationShare {
  share_id: string;
  share_name: string;
}

export interface Invitation {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string | null;
  share: string;
  share_name: string | null;
  is_viewer: boolean;
  expires_at: string;
  created_at: string | null;
}

export const invitationsApi = {
  validate: (token: string, signal?: AbortSignal) =>
    apiRequest<InvitationTokenInfo>(`/api/invitations/validate?token=${encodeURIComponent(token)}`, { signal }),
  accept: (input: {
    token: string;
    first_name: string;
    last_name: string;
    email: string;
    phone_number: string | null;
  }) => apiRequest<void>("/api/invitations/accept", jsonRequest("POST", input)),
  list: (signal?: AbortSignal) => apiRequest<Invitation[]>("/api/invitations", { signal }),
  availableShares: (signal?: AbortSignal) =>
    apiRequest<AvailableInvitationShare[]>("/api/invitations/available-shares", { signal }),
  create: (input: {
    email: string;
    share: string;
    first_name: string;
    last_name: string;
    phone_number: string | null;
    is_viewer: boolean;
  }) => apiRequest<Invitation>("/api/invitations", jsonRequest("POST", input)),
  revoke: (id: string) => apiRequest<void>(`/api/invitations/${id}`, { method: "DELETE" }),
};
