import { useCallback, useReducer, useRef } from "react";
import type { CancelResult, RefundPreview, Reservation } from "../types";

interface CancelFlowState {
  confirmId: number | null;
  deletingId: number | null;
  error: string | null;
  preview: RefundPreview | null;
  loadingPreview: boolean;
  successMessage: string | null;
}

type CancelFlowAction =
  | { type: "START_PREVIEW"; id: number }
  | { type: "PREVIEW_LOADED"; id: number; preview: RefundPreview }
  | { type: "PREVIEW_FAILED"; id: number; error: string }
  | { type: "START_CANCEL"; id: number }
  | { type: "CANCEL_SUCCESS"; message: string }
  | { type: "CANCEL_FAILED"; error: string }
  | { type: "DISMISS" }
  | { type: "RESET" };

const initialState: CancelFlowState = {
  confirmId: null,
  deletingId: null,
  error: null,
  preview: null,
  loadingPreview: false,
  successMessage: null,
};

function reducer(state: CancelFlowState, action: CancelFlowAction): CancelFlowState {
  switch (action.type) {
    case "START_PREVIEW":
      return {
        ...initialState,
        confirmId: action.id,
        loadingPreview: true,
      };
    case "PREVIEW_LOADED":
      if (state.confirmId !== action.id) return state;
      return { ...state, preview: action.preview, loadingPreview: false };
    case "PREVIEW_FAILED":
      if (state.confirmId !== action.id) return state;
      return { ...state, error: action.error, preview: null, loadingPreview: false };
    case "START_CANCEL":
      return { ...state, deletingId: action.id, error: null };
    case "CANCEL_SUCCESS":
      return { ...initialState, successMessage: action.message };
    case "CANCEL_FAILED":
      return { ...state, deletingId: null, error: action.error };
    case "DISMISS":
      return { ...state, confirmId: null, preview: null, loadingPreview: false };
    case "RESET":
      return initialState;
  }
}

export function useCancelFlow(
  previewRefund: (id: number) => Promise<RefundPreview>,
  cancelReservation: (id: number) => Promise<CancelResult>,
  onCancelled: () => void,
) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const stateRef = useRef(state);
  stateRef.current = state;

  const startPreview = useCallback(async (reservation: Reservation) => {
    if (stateRef.current.confirmId === reservation.id) {
      dispatch({ type: "DISMISS" });
      return;
    }

    const targetId = reservation.id;
    dispatch({ type: "START_PREVIEW", id: targetId });

    try {
      const preview = await previewRefund(targetId);
      dispatch({ type: "PREVIEW_LOADED", id: targetId, preview });
    } catch (err) {
      dispatch({
        type: "PREVIEW_FAILED",
        id: targetId,
        error: err instanceof Error ? err.message : "Failed to load cancellation policy",
      });
    }
  }, [previewRefund]);

  const confirmCancel = useCallback(async (reservation: Reservation) => {
    const { preview } = stateRef.current;
    if (!preview || !preview.cancellation_eligible) return;

    dispatch({ type: "START_CANCEL", id: reservation.id });

    try {
      const result = await cancelReservation(reservation.id);
      dispatch({ type: "CANCEL_SUCCESS", message: result.message });
      onCancelled();
    } catch (err) {
      dispatch({
        type: "CANCEL_FAILED",
        error: err instanceof Error ? err.message : "Failed to cancel reservation",
      });
    }
  }, [cancelReservation, onCancelled]);

  const dismiss = useCallback(() => dispatch({ type: "DISMISS" }), []);
  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, startPreview, confirmCancel, dismiss, reset };
}

export function isCancellationBlocked(preview: RefundPreview | null): boolean {
  if (!preview) return true;
  return !preview.cancellation_eligible;
}

export function getPolicyNoteClassName(reservation: Reservation, preview: RefundPreview): string {
  if (reservation.status === "paid") {
    return `reservation-cancel-prompt ${preview.eligible ? "refund-eligible" : "refund-ineligible"}`;
  }
  if (reservation.status === "reserved") {
    return `reservation-cancel-prompt ${preview.cancellation_eligible ? "refund-eligible" : "refund-ineligible"}`;
  }
  return "reservation-cancel-detail";
}

export function getConfirmButtonLabel(reservation: Reservation, preview: RefundPreview | null): string {
  if (reservation.status === "paid" && preview?.eligible) return "Cancel & Refund";
  return "Yes, Cancel Trip";
}
