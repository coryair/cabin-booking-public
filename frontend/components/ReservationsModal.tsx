import { useEffect, useMemo, useState } from "react";
import { useAllReservations } from "../hooks/useAllReservations";
import { useCancelFlow, isCancellationBlocked, getPolicyNoteClassName, getConfirmButtonLabel } from "../hooks/useCancelFlow";
import { useAppData } from "../context/AppDataContext";
import { getCabinName, formatDate } from "../utils";
import { GuestAdjustmentModal } from "./GuestAdjustmentModal";
import type { Reservation } from "../types";

interface ReservationsModalProps {
  onClose: () => void;
  onReservationDeleted: () => void;
  effectiveToday?: string;
}

export function ReservationsModal({ onClose, onReservationDeleted, effectiveToday }: ReservationsModalProps) {
  const [activeTab, setActiveTab] = useState<"upcoming" | "past">("upcoming");
  const [onlyShowMyReservations, setOnlyShowMyReservations] = useState(false);
  const [guestEditResult, setGuestEditResult] = useState<string | null>(null);
  const [editingGuestReservation, setEditingGuestReservation] = useState<Reservation | null>(null);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [payingReservationId, setPayingReservationId] = useState<number | null>(null);
  const {
    shareholder,
    isAdmin,
    bookingStatus,
    cabins,
    refreshBookingStatus,
    activeShareId,
    activeShare,
  } = useAppData();

  const {
    reservations,
    isLoading,
    error,
    cancelReservation,
    resumeCheckout,
    previewRefund,
    previewGuestAdjustment,
    startGuestAdjustmentCheckout,
    applyGuestAdjustment,
    refundGuestAdjustment,
  } = useAllReservations(activeShareId ?? undefined);

  const cancel = useCancelFlow(previewRefund, cancelReservation, () => {
    onReservationDeleted();
    refreshBookingStatus();
  });
  const resetCancel = cancel.reset;

  const today = useMemo(() => {
    if (effectiveToday) return effectiveToday;
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }, [effectiveToday]);

  const currentShareholderId = shareholder?.id ?? null;

  const { upcoming, past } = useMemo(() => {
    const upcoming: Reservation[] = [];
    const past: Reservation[] = [];

    for (const r of reservations) {
      // Filter out cancelled/refunded from upcoming, show in past
      if (r.status === "cancelled" || r.status === "refunded") {
        past.push(r);
        continue;
      }
      if (r.end_date >= today) {
        upcoming.push(r);
      } else {
        past.push(r);
      }
    }

    // Sort upcoming by start_date ascending
    upcoming.sort((a, b) => a.start_date.localeCompare(b.start_date));
    // Sort past by start_date descending
    past.sort((a, b) => b.start_date.localeCompare(a.start_date));

    return { upcoming, past };
  }, [reservations, today]);

  const displayedReservations = useMemo(() => {
    const source = activeTab === "upcoming" ? upcoming : past;

    if (!onlyShowMyReservations || currentShareholderId == null) return source;

    return source.filter((reservation) => reservation.booked_by_shareholder_id === currentShareholderId);
  }, [activeTab, currentShareholderId, onlyShowMyReservations, past, upcoming]);

  const formatReservationDate = (dateStr: string) =>
    formatDate(dateStr, { month: "short", day: "numeric", year: "numeric" });

  const getStayLabel = (reservation: Reservation) => {
    if (reservation.is_day_use) return "Day use";
    const startTime = new Date(`${reservation.start_date}T00:00:00`).getTime();
    const endTime = new Date(`${reservation.end_date}T00:00:00`).getTime();
    const nights = Math.max(1, Math.round((endTime - startTime) / 86400000));
    return `${nights} ${nights === 1 ? "night" : "nights"}`;
  };

  const getCabinBorderClass = (cabinIds: string[]) => {
    if (cabinIds.length > 1) {
      return "both";
    }
    return cabinIds[0] || "";
  };

  const isCancelled = (r: Reservation) => r.status === "cancelled" || r.status === "refunded";
  const isUnpaid = (r: Reservation) => r.status === "unpaid";
  const canManageReservation = (reservation: Reservation) => (
    isAdmin || (currentShareholderId != null && reservation.booked_by_shareholder_id === currentShareholderId)
  );

  const handleResumePayment = async (reservation: Reservation) => {
    setPaymentError(null);
    setGuestEditResult(null);
    setPayingReservationId(reservation.id);
    try {
      const result = await resumeCheckout(reservation.id);
      if (result.status === "paid") {
        setGuestEditResult("Payment already confirmed.");
        onReservationDeleted();
        refreshBookingStatus();
        return;
      }
      if (!result.checkout_url) {
        throw new Error("Payment setup did not return a checkout link");
      }
      window.location.href = result.checkout_url;
    } catch (err) {
      setPaymentError(err instanceof Error ? err.message : "Failed to resume payment");
      setPayingReservationId(null);
    }
  };

  useEffect(() => {
    resetCancel();
    setPaymentError(null);
  }, [activeTab, onlyShowMyReservations, resetCancel]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal reservations-modal" onClick={(e) => e.stopPropagation()}>
        <h3>MY RESERVATIONS</h3>
        <p className="reservations-intro">
          View upcoming and past reservations for {activeShare?.share_name || "this share"}, see who booked each stay, and use the filter to switch between only your reservations and all reservations for that share.
        </p>

        <div className="reservations-tabs">
          <button
            className={`tab-btn ${activeTab === "upcoming" ? "active" : ""}`}
            onClick={() => setActiveTab("upcoming")}
          >
            Upcoming ({upcoming.length})
          </button>
          <button
            className={`tab-btn ${activeTab === "past" ? "active" : ""}`}
            onClick={() => setActiveTab("past")}
          >
            Past ({past.length})
          </button>
        </div>

        {activeShare && (
          <label className="reservations-share-toggle">
            <input
              type="checkbox"
              checked={onlyShowMyReservations}
              onChange={(e) => setOnlyShowMyReservations(e.target.checked)}
            />
            <span>Only show my reservations for {activeShare.share_name}</span>
          </label>
        )}

        {bookingStatus && bookingStatus.season_max_nights > 0 && ["round_1", "round_2", "round_3"].includes(bookingStatus.current_round) && (
          <div className="priority-nights-summary">
            {bookingStatus.nights_used} / {bookingStatus.season_max_nights} priority round nights used
          </div>
        )}
        {cancel.state.error && <div className="modal-error">{cancel.state.error}</div>}
        {paymentError && <div className="modal-error">{paymentError}</div>}
        {cancel.state.successMessage && <div className="modal-success">{cancel.state.successMessage}</div>}
        {guestEditResult && <div className="modal-success">{guestEditResult}</div>}

        <div className="reservations-list">
          {isLoading ? (
            <div className="modal-loading">
              <div className="spinner" />
              <p>Loading reservations...</p>
            </div>
          ) : error ? (
            <div className="modal-error">{error}</div>
          ) : displayedReservations.length === 0 ? (
            <div className="no-reservations">
              <div className="no-reservations-icon" aria-hidden="true">
                {activeTab === "upcoming" ? (
                  <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L8 18l-4 1 1-4z" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="9" />
                    <path d="M12 7v5l3 2" />
                  </svg>
                )}
              </div>
              <p className="no-reservations-title">
                {activeTab === "upcoming"
                  ? onlyShowMyReservations
                    ? "No upcoming trips booked by you yet"
                    : `No upcoming trips for ${activeShare?.share_name || "this share"} yet`
                  : onlyShowMyReservations
                    ? "No past trips booked by you in the log"
                    : `No past trips for ${activeShare?.share_name || "this share"} in the log`}
              </p>
              {activeTab === "upcoming" && (
                <p className="no-reservations-subtitle">Time to plan your next Cabin Booking adventure.</p>
              )}
            </div>
          ) : (
            displayedReservations.map((reservation) => {
              const isConfirming = cancel.state.confirmId === reservation.id;
              const preview = isConfirming ? cancel.state.preview : null;
              const blocked = isCancellationBlocked(preview);

              return (
                <div
                  key={reservation.id}
                  className={`reservation-card ${getCabinBorderClass(reservation.cabins)}${isCancelled(reservation) ? " cancelled" : ""}`}
                >
                  <div className="reservation-card-header">
                    {reservation.cabins.map((cabinId) => (
                      <span key={cabinId} className={`cabin-badge ${cabinId}`}>
                        {getCabinName(cabins, cabinId)}
                      </span>
                    ))}
                    {isCancelled(reservation) && (
                      <span className={`status-badge ${reservation.status}`}>
                        {reservation.status === "refunded" ? "Refunded" : "Cancelled"}
                      </span>
                    )}
                    {isUnpaid(reservation) && (
                      <span className="status-badge unpaid">Payment Due</span>
                    )}
                  </div>
                  <div className="reservation-card-body">
                    <div className="reservation-dates-row">
                      <div className="reservation-dates">
                        {formatReservationDate(reservation.start_date)}{!reservation.is_day_use && ` - ${formatReservationDate(reservation.end_date)}`}
                      </div>
                      <div className="reservation-stay-type">{getStayLabel(reservation)}</div>
                    </div>
                    {reservation.booked_by_shareholder_name && (
                      <div className="reservation-booked-by">
                        Booked by {reservation.booked_by_shareholder_name}
                      </div>
                    )}
                    <div className="reservation-meta-row">
                      {reservation.guest_count > 0 && (
                        <div className="reservation-guest">
                          +{reservation.guest_count} {reservation.guest_count === 1 ? "guest" : "guests"}
                        </div>
                      )}
                      <div className="reservation-cost">
                        ${reservation.cost.toFixed(2)}
                      </div>
                    </div>
                    {reservation.status === "refunded" && reservation.refund_amount != null && (
                      <div className="reservation-refund-info">
                        Refunded: ${reservation.refund_amount.toFixed(2)}
                      </div>
                    )}
                  </div>
                  {!isCancelled(reservation) && canManageReservation(reservation) && (activeTab === "upcoming" || !isUnpaid(reservation)) && (
                    <div className="reservation-card-actions">
                      {activeTab === "upcoming" && isConfirming ? (
                        <div className="reservation-cancel-confirm">
                          {cancel.state.loadingPreview ? (
                            <p className="reservation-cancel-prompt">Loading cancellation policy...</p>
                          ) : preview && (blocked || preview.admin_override) ? (
                            <p className={getPolicyNoteClassName(reservation, preview)}>
                              {preview.reason}
                            </p>
                          ) : null}
                          <div className="reservation-cancel-buttons">
                            {!blocked && (
                              <button
                                className="cancel-reservation-confirm-btn"
                                onClick={() => void cancel.confirmCancel(reservation)}
                                disabled={cancel.state.deletingId === reservation.id || cancel.state.loadingPreview}
                              >
                                {cancel.state.deletingId === reservation.id ? "Canceling..." : getConfirmButtonLabel(reservation, preview)}
                              </button>
                            )}
                            <button
                              className="cancel-reservation-keep-btn"
                              onClick={cancel.dismiss}
                              disabled={cancel.state.deletingId === reservation.id}
                            >
                              {blocked ? "Close" : "Keep It"}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          {activeTab === "upcoming" && isUnpaid(reservation) && (
                            <button
                              className="pay-reservation-btn"
                              onClick={() => void handleResumePayment(reservation)}
                              disabled={payingReservationId !== null || cancel.state.deletingId !== null}
                            >
                              {payingReservationId === reservation.id ? "Opening..." : "Pay Now"}
                            </button>
                          )}
                          {!isUnpaid(reservation) && (
                            <button
                              className="cancel-reservation-btn"
                              onClick={() => {
                                cancel.reset();
                                setPaymentError(null);
                                setGuestEditResult(null);
                                setEditingGuestReservation(reservation);
                              }}
                              disabled={cancel.state.deletingId !== null}
                            >
                              Edit Guests
                            </button>
                          )}
                          {activeTab === "upcoming" && (
                            <button
                              className="cancel-reservation-btn"
                              onClick={() => {
                                setPaymentError(null);
                                void cancel.startPreview(reservation);
                              }}
                              disabled={cancel.state.deletingId !== null || payingReservationId !== null}
                            >
                              Cancel
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

      <div className="modal-actions">
        <button onClick={onClose} className="cancel-btn">
          Close
        </button>
      </div>
    </div>
      {editingGuestReservation && (
        <GuestAdjustmentModal
          reservation={editingGuestReservation}
          onClose={() => setEditingGuestReservation(null)}
          onSaved={(result) => {
            setGuestEditResult(result.message);
            onReservationDeleted();
          }}
          previewGuestAdjustment={previewGuestAdjustment}
          startGuestAdjustmentCheckout={startGuestAdjustmentCheckout}
          applyGuestAdjustment={applyGuestAdjustment}
          refundGuestAdjustment={refundGuestAdjustment}
          isAdmin={isAdmin}
        />
      )}
    </div>
  );
}
