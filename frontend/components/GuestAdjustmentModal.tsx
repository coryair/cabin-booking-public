import { useEffect, useMemo, useState } from "react";
import { GuestNightsEditor } from "./GuestNightsEditor";
import type {
  Reservation,
  GuestAdjustmentPreview,
  GuestAdjustmentCheckoutResult,
  GuestAdjustmentApplyResult,
} from "../types";

interface GuestAdjustmentModalProps {
  reservation: Reservation;
  onClose: () => void;
  onSaved?: (result: GuestAdjustmentApplyResult) => void;
  previewGuestAdjustment: (id: number, guestNights: number[]) => Promise<GuestAdjustmentPreview>;
  startGuestAdjustmentCheckout: (id: number, guestNights: number[]) => Promise<GuestAdjustmentCheckoutResult>;
  applyGuestAdjustment: (id: number, guestNights: number[]) => Promise<GuestAdjustmentApplyResult>;
  refundGuestAdjustment: (id: number, guestNights: number[]) => Promise<GuestAdjustmentApplyResult>;
  isAdmin?: boolean;
}

function getStayUnits(reservation: Reservation): number {
  const start = new Date(`${reservation.start_date}T00:00:00`).getTime();
  const end = new Date(`${reservation.end_date}T00:00:00`).getTime();
  return Math.max(1, Math.round((end - start) / 86400000));
}

function fallbackGuestNights(reservation: Reservation): number[] {
  if (reservation.guest_nights && reservation.guest_nights.length >= 0) return [...reservation.guest_nights];
  const units = getStayUnits(reservation);
  return Array.from({ length: reservation.guest_count || 0 }, () => units);
}

export function GuestAdjustmentModal({
  reservation,
  onClose,
  onSaved,
  previewGuestAdjustment,
  startGuestAdjustmentCheckout,
  applyGuestAdjustment,
  refundGuestAdjustment,
  isAdmin = false,
}: GuestAdjustmentModalProps) {
  const [guestNights, setGuestNights] = useState<number[]>(() => fallbackGuestNights(reservation));
  const [preview, setPreview] = useState<GuestAdjustmentPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const maxUnits = useMemo(() => getStayUnits(reservation), [reservation]);

  useEffect(() => {
    let cancelled = false;
    setLoadingPreview(true);
    setError(null);
    previewGuestAdjustment(reservation.id, guestNights)
      .then((result) => {
        if (!cancelled) setPreview(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to preview guest changes");
      })
      .finally(() => {
        if (!cancelled) setLoadingPreview(false);
      });
    return () => { cancelled = true; };
  }, [guestNights, previewGuestAdjustment, reservation.id]);

  const handlePrimary = async () => {
    if (!preview) return;
    setSubmitting(true);
    setError(null);
    try {
      if (isAdmin) {
        // Admin bypasses payment - apply directly
        const result = await applyGuestAdjustment(reservation.id, guestNights);
        onSaved?.(result);
        onClose();
        return;
      }
      if (preview.action === "collect") {
        const result = await startGuestAdjustmentCheckout(reservation.id, guestNights);
        window.location.href = result.checkout_url;
        return;
      }
      if (preview.action === "refund") {
        const result = await refundGuestAdjustment(reservation.id, guestNights);
        onSaved?.(result);
        onClose();
        return;
      }
      const result = await applyGuestAdjustment(reservation.id, guestNights);
      onSaved?.(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update guests");
    } finally {
      setSubmitting(false);
    }
  };

  const primaryLabel = isAdmin
    ? "Save Guest Changes"
    : preview?.action === "collect"
      ? "Continue to Payment"
      : preview?.action === "refund"
        ? "Update & Refund"
        : "Save Guest Changes";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal reservations-modal guest-adjustment-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Edit Guests</h3>
        <p className="field-hint" style={{ marginTop: -6 }}>Add or remove guests and adjust how many nights each one is staying. You only pay for the nights a guest actually uses.{preview?.edit_deadline ? ` Edits are allowed through ${preview.edit_deadline} (30 days after check-in).` : ""}</p>

        <GuestNightsEditor
          helperText=""
          guestNights={guestNights}
          onChange={setGuestNights}
          maxUnits={maxUnits}
          disabled={submitting}
        />

        {loadingPreview ? (
          <div className="modal-loading">
            <div className="spinner" />
            <p>Calculating changes...</p>
          </div>
        ) : preview ? (
          <div className="cost-display" style={{ marginTop: 8 }}>
            {!preview.allowed && preview.reason && (
              <div className="booking-blocked-msg" style={{ marginBottom: 8 }}>{preview.reason}</div>
            )}
            <div className="cost-row">
              <span>Current Total</span>
              <span>${preview.current_total.toFixed(2)}</span>
            </div>
            <div className="cost-row">
              <span>Updated Total</span>
              <span>${preview.updated_total.toFixed(2)}</span>
            </div>
            <div className="cost-row">
              <span>Guest fee ({preview.updated_guest_nights_total} guest-nights)</span>
              <span>${preview.updated_guest_fee.toFixed(2)}</span>
            </div>
            {preview.action === "collect" && (
              <div className="cost-row total">
                <span>Additional Charge</span>
                <span>${preview.charge_amount.toFixed(2)}</span>
              </div>
            )}
            {preview.action === "refund" && (
              <>
                {preview.requested_refund_amount > 0 && (
                  <div className="cost-row">
                    <span>Requested Refund</span>
                    <span>${preview.requested_refund_amount.toFixed(2)}</span>
                  </div>
                )}
                <div className="cost-row total refund">
                  <span>Approved Refund Amount</span>
                  <span>${preview.refund_amount.toFixed(2)}</span>
                </div>
                {preview.processing_fee_retained > 0 && (
                  <div className="cost-row">
                    <span>4% Fee Retained (This Refund)</span>
                    <span>${preview.processing_fee_retained.toFixed(2)}</span>
                  </div>
                )}
                {preview.processing_fee_retained_total > 0 && (
                  <div className="cost-row">
                    <span>Total Fee Retained So Far</span>
                    <span>${preview.processing_fee_retained_total.toFixed(2)} / ${preview.policy_fee_target.toFixed(2)}</span>
                  </div>
                )}
                <p className="field-hint" style={{ marginTop: 8 }}>
                  Refund applies 4% fee retention policy and caps retention so total retained fee does not exceed the booking fee charged.
                </p>
              </>
            )}
            {preview.action === "none" && (
              <div className="cost-row total">
                <span>No Charge Change</span>
                <span>$0.00</span>
              </div>
            )}
          </div>
        ) : null}

        {error && <div className="modal-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="cancel-btn" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            type="button"
            className="confirm-btn"
            onClick={handlePrimary}
            disabled={submitting || loadingPreview || !preview || !preview.allowed}
          >
            {submitting ? "Processing..." : primaryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
