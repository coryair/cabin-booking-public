import type {
  CancelResult,
  GuestAdjustmentApplyResult,
  GuestAdjustmentCheckoutResult,
  GuestAdjustmentPreview,
  GuestAdjustmentReconcileResult,
  RefundPreview,
  Reservation,
  ReservationAdminUpdate,
} from "../types";
import { apiRequest, jsonRequest } from "./client";

export interface ResumeCheckoutResult {
  status: "requires_payment" | "paid";
  reservation_id: number;
  checkout_url?: string | null;
}

export interface CheckoutResult {
  checkout_url: string;
  reservation_id: number;
}

function reservationListUrl(options: { shareId?: string; includeCancelled?: boolean } = {}): string {
  const params = new URLSearchParams();
  if (options.shareId) params.set("share", options.shareId);
  if (options.includeCancelled) params.set("include_cancelled", "true");
  const query = params.toString();
  return query ? `/api/reservations?${query}` : "/api/reservations";
}

export const reservationsApi = {
  list: (options: { shareId?: string; includeCancelled?: boolean; signal?: AbortSignal } = {}) =>
    apiRequest<Reservation[]>(reservationListUrl(options), { signal: options.signal }),
  get: (id: number | string, signal?: AbortSignal) =>
    apiRequest<Reservation>(`/api/reservations/${id}`, { signal }),
  update: (id: number, update: ReservationAdminUpdate) =>
    apiRequest<Reservation>(`/api/reservations/${id}`, jsonRequest("PUT", update)),
  cancel: (id: number) =>
    apiRequest<CancelResult>(`/api/reservations/${id}/cancel`, { method: "POST" }),
  refundPreview: (id: number) =>
    apiRequest<RefundPreview>(`/api/reservations/${id}/refund-preview`),
  adminRefund: (id: number, overridePolicy: boolean) =>
    apiRequest<CancelResult>(
      `/api/reservations/${id}/refund`,
      jsonRequest("POST", { override_policy: overridePolicy }),
    ),
  resumeCheckout: (id: number) =>
    apiRequest<ResumeCheckoutResult>("/api/checkout/resume", jsonRequest("POST", { reservation_id: id })),
  checkout: (input: unknown) =>
    apiRequest<CheckoutResult>("/api/checkout", jsonRequest("POST", input)),
  reconcileCheckout: (id: number) =>
    apiRequest<{ status: "paid" | "unpaid" }>("/api/checkout/reconcile", jsonRequest("POST", { reservation_id: id })),
  guestAdjustmentPreview: (id: number, guestNights: number[]) =>
    apiRequest<GuestAdjustmentPreview>(`/api/reservations/${id}/guest-adjustment-preview`, jsonRequest("POST", { guest_nights: guestNights })),
  guestAdjustmentCheckout: (id: number, guestNights: number[]) =>
    apiRequest<GuestAdjustmentCheckoutResult>(`/api/reservations/${id}/guest-adjustment-checkout`, jsonRequest("POST", { guest_nights: guestNights })),
  guestAdjustmentApply: (id: number, guestNights: number[]) =>
    apiRequest<GuestAdjustmentApplyResult>(`/api/reservations/${id}/guest-adjustment-apply`, jsonRequest("POST", { guest_nights: guestNights })),
  guestAdjustmentRefund: (id: number, guestNights: number[]) =>
    apiRequest<GuestAdjustmentApplyResult>(`/api/reservations/${id}/guest-adjustment-refund`, jsonRequest("POST", { guest_nights: guestNights })),
  guestAdjustmentReconcile: (reservationId: number, adjustmentId: number) =>
    apiRequest<GuestAdjustmentReconcileResult>(`/api/reservations/${reservationId}/guest-adjustment-reconcile`, jsonRequest("POST", { adjustment_id: adjustmentId })),
  cancelGuestAdjustment: (adjustmentId: number) =>
    apiRequest<void>(`/api/guest-adjustments/${adjustmentId}/cancel`, { method: "POST" }),
  sendPaymentEmail: (reservationId: number) =>
    apiRequest<{ booker_name?: string }>(`/api/reservations/${reservationId}/send-payment-email`, { method: "POST" }),
};
