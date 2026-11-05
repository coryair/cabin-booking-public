import { useState, useEffect, useCallback } from "react";
import type {
  Reservation,
  RefundPreview,
  CancelResult,
  GuestAdjustmentPreview,
  GuestAdjustmentCheckoutResult,
  GuestAdjustmentApplyResult,
  GuestAdjustmentReconcileResult,
} from "../types";
import { reservationsApi, type ResumeCheckoutResult } from "../api/reservations";

export function useAllReservations(shareId?: string) {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchReservations = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await reservationsApi.list({ shareId, signal });
      if (!signal?.aborted) setReservations(Array.isArray(data) ? data : []);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (!signal?.aborted) setIsLoading(false);
    }
  }, [shareId]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchReservations(controller.signal);
    return () => controller.abort();
  }, [fetchReservations]);

  const cancelReservation = async (id: number): Promise<CancelResult> => {
    const data = await reservationsApi.cancel(id);
    await fetchReservations();
    return data as CancelResult;
  };

  const previewRefund = async (id: number): Promise<RefundPreview> => {
    return reservationsApi.refundPreview(id);
  };

  const deleteReservation = async (id: number): Promise<void> => {
    await cancelReservation(id);
  };

  const resumeCheckout = async (id: number): Promise<ResumeCheckoutResult> => {
    const data = await reservationsApi.resumeCheckout(id);
    if (data.status === "paid") await fetchReservations();
    return data;
  };

  const previewGuestAdjustment = async (id: number, guestNights: number[]): Promise<GuestAdjustmentPreview> => {
    return reservationsApi.guestAdjustmentPreview(id, guestNights);
  };

  const startGuestAdjustmentCheckout = async (id: number, guestNights: number[]): Promise<GuestAdjustmentCheckoutResult> => {
    return reservationsApi.guestAdjustmentCheckout(id, guestNights);
  };

  const applyGuestAdjustment = async (id: number, guestNights: number[]): Promise<GuestAdjustmentApplyResult> => {
    const data = await reservationsApi.guestAdjustmentApply(id, guestNights);
    await fetchReservations();
    return data as GuestAdjustmentApplyResult;
  };

  const refundGuestAdjustment = async (id: number, guestNights: number[]): Promise<GuestAdjustmentApplyResult> => {
    const data = await reservationsApi.guestAdjustmentRefund(id, guestNights);
    await fetchReservations();
    return data as GuestAdjustmentApplyResult;
  };

  const reconcileGuestAdjustment = async (reservationId: number, adjustmentId: number): Promise<GuestAdjustmentReconcileResult> => {
    const data = await reservationsApi.guestAdjustmentReconcile(reservationId, adjustmentId);
    await fetchReservations();
    return data as GuestAdjustmentReconcileResult;
  };

  return {
    reservations,
    isLoading,
    error,
    refresh: fetchReservations,
    deleteReservation,
    cancelReservation,
    resumeCheckout,
    previewRefund,
    previewGuestAdjustment,
    startGuestAdjustmentCheckout,
    applyGuestAdjustment,
    refundGuestAdjustment,
    reconcileGuestAdjustment,
  };
}
