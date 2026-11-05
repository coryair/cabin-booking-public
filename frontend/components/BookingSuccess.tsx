import { useState, useEffect } from "react";
import { formatDate } from "../utils";
import type { Reservation } from "../types";
import { reservationsApi } from "../api/reservations";

interface BookingSuccessProps {
  reservationId: string;
  adjustmentId?: string | null;
  onReturn: () => void;
}

const MAX_POLLS = 20;

export function BookingSuccess({ reservationId, adjustmentId, onReturn }: BookingSuccessProps) {
  const [reservation, setReservation] = useState<Reservation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [adjustmentPending, setAdjustmentPending] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const fetchReservation = async () => {
      try {
        let shouldPollAdjustment = false;
        const data = await reservationsApi.get(reservationId);

        if (data.status === "unpaid") {
          try {
            const reconciled = await reservationsApi.reconcileCheckout(Number(reservationId));
            if (reconciled.status === "paid") {
              const paidData = await reservationsApi.get(reservationId);
              setReservation(paidData);
              setError(null);
              return;
            }
          } catch {
            // Webhook reconciliation can lag briefly; continue polling below.
          }
        }

        if (adjustmentId) {
          try {
            const adjustmentResult = await reservationsApi.guestAdjustmentReconcile(
              Number(reservationId),
              Number(adjustmentId),
            );
            if (adjustmentResult.status === "paid") {
              setAdjustmentPending(false);
              const updated = await reservationsApi.get(reservationId);
              setReservation(updated);
              setError(null);
              return;
            }
            if (adjustmentResult.status === "failed" || adjustmentResult.status === "cancelled") {
              setError("Guest adjustment payment was not completed.");
              return;
            }
            shouldPollAdjustment = adjustmentResult.status === "pending";
            setAdjustmentPending(shouldPollAdjustment);
          } catch {
            shouldPollAdjustment = true;
            setAdjustmentPending(true);
          }
        }

        setReservation(data);
        setError(null);

        // If still unpaid and we haven't polled too many times, poll again
        if ((data.status === "unpaid" || shouldPollAdjustment) && pollCount < MAX_POLLS && !cancelled) {
          setTimeout(() => {
            if (!cancelled) setPollCount((c) => c + 1);
          }, 2000);
        }
      } catch {
        setError("Could not load reservation details.");
      }
    };

    fetchReservation();
    return () => { cancelled = true; };
  }, [reservationId, adjustmentId, pollCount]);

  const isPaid = reservation?.status === "paid" && !adjustmentPending;
  const isProcessing = reservation?.status === "unpaid" || adjustmentPending;
  const isDelayed = isProcessing && pollCount >= MAX_POLLS;

  const cabinStr = reservation?.cabins?.map((c) => c.charAt(0).toUpperCase() + c.slice(1)).join(" & ") ?? "";
  const nights = reservation
    ? Math.round(
        (new Date(reservation.end_date + "T00:00:00").getTime() -
          new Date(reservation.start_date + "T00:00:00").getTime()) / 86400000
      )
    : 0;
  const stayLabel = reservation?.is_day_use
    ? "Day Use"
    : `${nights} night${nights !== 1 ? "s" : ""}`;

  return (
    <div className="app">
      <div className="booking-success">
        <div className="booking-success-card">
          {error ? (
            <>
              <div className="wizard-result failed">
                <svg className="wizard-result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M15 9l-6 6M9 9l6 6" />
                </svg>
                <h3 className="wizard-result-title">Something went wrong</h3>
                <p className="wizard-result-error">{error}</p>
              </div>
            </>
          ) : !reservation ? (
            <div className="modal-loading">
              <div className="spinner" />
              <p>Loading reservation...</p>
            </div>
          ) : isProcessing ? (
            <div className="modal-loading">
              <div className="spinner" />
              <p>{isDelayed ? "Payment is taking longer than expected." : "Processing payment..."}</p>
              <p className="field-hint">
                {isDelayed ? "Tap Check Again to refresh payment status." : "This usually takes just a moment."}
              </p>
            </div>
          ) : isPaid ? (
            <>
              <div className="wizard-result success">
                <svg className="wizard-result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M8 12l3 3 5-5" />
                </svg>
                <h3 className="wizard-result-title">{adjustmentId ? "Guest Update Confirmed" : "Payment Confirmed"}</h3>
                <p className="wizard-result-detail">
                  {cabinStr} &mdash; {stayLabel}
                </p>
              </div>
              <div className="cost-display" style={{ marginTop: "16px" }}>
                <div className="cost-row">
                  <span>Dates</span>
                  <span>
                    {formatDate(reservation.start_date, { month: "short", day: "numeric" })}
                    {!reservation.is_day_use && (
                      <>
                        {" "}&rarr;{" "}
                        {formatDate(reservation.end_date, { month: "short", day: "numeric" })}
                      </>
                    )}
                  </span>
                </div>
                <div className="cost-row">
                  <span>Confirmation #</span>
                  <span>{reservation.id}</span>
                </div>
                <div className="cost-row total">
                  <span>Total Paid</span>
                  <span>${reservation.cost.toFixed(2)}</span>
                </div>
              </div>
              <p className="field-hint" style={{ marginTop: "12px", textAlign: "center" }}>
                {adjustmentId ? "Your guest adjustment has been applied." : "A confirmation email has been sent to your inbox."}
              </p>
            </>
          ) : (
            // status === "reserved" (admin-created, no payment)
            <div className="wizard-result success">
              <svg className="wizard-result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M8 12l3 3 5-5" />
              </svg>
              <h3 className="wizard-result-title">Booking Confirmed</h3>
              <p className="wizard-result-detail">{cabinStr}</p>
            </div>
          )}
          <div className="wizard-actions" style={{ marginTop: "24px" }}>
            {isDelayed && (
              <button onClick={() => setPollCount(0)} className="back-btn">
                Check Again
              </button>
            )}
            <button onClick={onReturn} className="confirm-btn" style={{ marginLeft: "auto" }}>
              Return to Calendar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
