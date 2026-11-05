import React, { useState, useEffect, useCallback } from "react";
import { InfoTip } from "../Tooltip";
import { AdminMobileRow } from "./AdminMobileRow";
import { GuestAdjustmentModal } from "../GuestAdjustmentModal";
import type {
  RefundPreview,
  Reservation,
  ReservationAdminUpdate,
  ReservationStatus,
} from "../../types";
import { reservationsApi } from "../../api/reservations";

interface EditModalProps {
  reservation: Reservation;
  onClose: () => void;
  onSave: (id: number, update: ReservationAdminUpdate) => Promise<void>;
}

function EditModal({ reservation, onClose, onSave }: EditModalProps) {
  const [formData, setFormData] = useState({
    start_date: reservation.start_date,
    end_date: reservation.end_date,
    status: reservation.status as ReservationStatus,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const update: ReservationAdminUpdate = {};
      if (formData.start_date !== reservation.start_date) update.start_date = formData.start_date;
      if (formData.end_date !== reservation.end_date) update.end_date = formData.end_date;
      if (formData.status !== reservation.status) update.status = formData.status;

      await onSave(reservation.id, update);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const isCancelled = reservation.status === "cancelled" || reservation.status === "refunded";
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal admin-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Edit Reservation</h3>
        <div className="reservation-info">
          <p><strong>Share:</strong> {reservation.share_name || reservation.share}</p>
          <p><strong>Cabins:</strong> {reservation.cabins.join(", ")}</p>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>{reservation.is_day_use ? "Date" : "Start Date"}</label>
              <input
                type="date"
                className="form-input"
                value={formData.start_date}
                onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                required
                disabled={isCancelled}
              />
            </div>
            {!reservation.is_day_use && (
              <div className="form-group">
                <label>End Date</label>
                <input
                  type="date"
                  className="form-input"
                  value={formData.end_date}
                  onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  required
                  disabled={isCancelled}
                />
              </div>
            )}
          </div>
          <div className="form-group">
            <label>Status</label>
            <select
              className="form-input"
              value={formData.status}
              onChange={(e) => setFormData({ ...formData, status: e.target.value as ReservationStatus })}
            >
              <option value="reserved">Reserved</option>
              <option value="unpaid">Unpaid</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
              <option value="refunded">Refunded</option>
            </select>
          </div>
          {reservation.refund_amount != null && (
            <div className="reservation-info" style={{ marginTop: 8 }}>
              <p><strong>Refund Amount:</strong> ${reservation.refund_amount.toFixed(2)}</p>
              {reservation.refunded_at && <p><strong>Refunded At:</strong> {reservation.refunded_at}</p>}
              {reservation.stripe_refund_id && <p><strong>Stripe Refund:</strong> {reservation.stripe_refund_id}</p>}
            </div>
          )}
          {error && <div className="modal-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="cancel-btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="confirm-btn" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface RefundModalProps {
  reservation: Reservation;
  preview: RefundPreview;
  refunding: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (overridePolicy: boolean) => Promise<void>;
}

function RefundModal({ reservation, preview, refunding, error, onClose, onConfirm }: RefundModalProps) {
  const overrideRequired = Boolean(preview.override_required);

  return (
    <div className="modal-overlay" onClick={refunding ? undefined : onClose}>
      <div className="modal admin-modal refund-modal" onClick={(event) => event.stopPropagation()}>
        <h3>Refund &amp; Cancel</h3>
        <div className="reservation-info">
          <p><strong>Reservation:</strong> #{reservation.id} · {reservation.share_name || reservation.share}</p>
          <p><strong>Dates:</strong> {reservation.is_day_use ? reservation.start_date : `${reservation.start_date} - ${reservation.end_date}`}</p>
        </div>

        {overrideRequired && (
          <div className="refund-policy-warning" role="alert">
            <strong>Policy override required</strong>
            <p>
              This reservation is {preview.days_until_checkin} days before check-in, which is less
              than the 15-day refund policy allows.
            </p>
          </div>
        )}

        <div className="refund-summary">
          <div><span>Refund to guest</span><strong>${preview.refund_amount.toFixed(2)}</strong></div>
          <div><span>Booking fee retained</span><strong>${preview.processing_fee_kept.toFixed(2)}</strong></div>
        </div>
        <p className="refund-modal-note">
          This will refund the Stripe payment and cancel the reservation. The dates will become available again.
        </p>
        {error && <div className="modal-error" role="alert">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="cancel-btn" onClick={onClose} disabled={refunding}>
            Keep Reservation
          </button>
          <button
            type="button"
            className={overrideRequired ? "refund-override-btn" : "refund-confirm-btn"}
            onClick={() => void onConfirm(overrideRequired)}
            disabled={refunding}
          >
            {refunding
              ? "Refunding..."
              : overrideRequired
                ? "Override Policy & Refund"
                : "Refund & Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}

function fuzzyMatch(query: string, text: string): boolean {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (t.includes(q)) return true;
  // Simple fuzzy: all query chars appear in order
  let qi = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  return qi === q.length;
}

function matchesSearch(r: Reservation, query: string): boolean {
  if (!query) return true;
  const fields = [
    r.share_name || r.share,
    r.booked_by_shareholder_name || "",
    ...r.cabins,
    r.start_date,
    r.end_date,
    r.status,
    r.booking_round || "",
    String(r.id),
  ];
  return fields.some((f) => fuzzyMatch(query, f));
}

type StatusFilter = "any" | ReservationStatus;
type CabinFilter = "any" | "pine" | "cedar";

export function ReservationsAdmin() {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingReservation, setEditingReservation] = useState<Reservation | null>(null);
  const [cancelling, setCancelling] = useState<number | null>(null);
  const [previewingRefund, setPreviewingRefund] = useState<number | null>(null);
  const [refunding, setRefunding] = useState(false);
  const [refundModal, setRefundModal] = useState<{ reservation: Reservation; preview: RefundPreview } | null>(null);
  const [refundError, setRefundError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "upcoming" | "past">("upcoming");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("any");
  const [cabinFilter, setCabinFilter] = useState<CabinFilter>("any");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guestEditMessage, setGuestEditMessage] = useState<string | null>(null);
  const [editingGuestReservation, setEditingGuestReservation] = useState<Reservation | null>(null);

  const fetchReservations = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await reservationsApi.list({ includeCancelled: true, signal });
      if (!signal?.aborted) setReservations(data);
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : "Failed to load reservations");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetchReservations(controller.signal);
    return () => controller.abort();
  }, [fetchReservations]);

  const handleSave = async (reservationId: number, update: ReservationAdminUpdate) => {
    await reservationsApi.update(reservationId, update);
    await fetchReservations();
  };

  const handleCancel = async (reservationId: number) => {
    if (!confirm("Are you sure you want to cancel this reservation?")) return;

    setCancelling(reservationId);
    setError(null);
    try {
      await reservationsApi.cancel(reservationId);
      await fetchReservations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel reservation");
    } finally {
      setCancelling(null);
    }
  };

  const openRefundModal = async (reservation: Reservation) => {
    setPreviewingRefund(reservation.id);
    setError(null);
    setRefundError(null);
    try {
      const preview = await reservationsApi.refundPreview(reservation.id);
      setRefundModal({ reservation, preview });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to preview refund");
    } finally {
      setPreviewingRefund(null);
    }
  };

  const handleRefund = async (overridePolicy: boolean) => {
    if (!refundModal) return;
    setRefunding(true);
    setRefundError(null);
    try {
      const result = await reservationsApi.adminRefund(refundModal.reservation.id, overridePolicy);
      setRefundModal(null);
      setGuestEditMessage(result.message);
      await fetchReservations();
    } catch (err) {
      setRefundError(err instanceof Error ? err.message : "Failed to refund reservation");
    } finally {
      setRefunding(false);
    }
  };

  const previewGuestAdjustment = reservationsApi.guestAdjustmentPreview;

  const startGuestAdjustmentCheckout = reservationsApi.guestAdjustmentCheckout;

  const applyGuestAdjustment = async (id: number, guestNights: number[]) => {
    const data = await reservationsApi.guestAdjustmentApply(id, guestNights);
    await fetchReservations();
    return data;
  };

  const refundGuestAdjustment = async (id: number, guestNights: number[]) => {
    const data = await reservationsApi.guestAdjustmentRefund(id, guestNights);
    await fetchReservations();
    return data;
  };

  const handleExport = () => {
    const headers = [
      "ID", "Share", "Share Name", "Booked By",
      "Start Date", "End Date", "Type",
      "Cabins", "Additional Guests",
      "Base Cost", "Guest Fee", "Processing Fee", "Total Cost",
      "Status", "Booking Round",
      "Created At", "Cancelled At", "Refund Amount", "Cancellation Reason",
    ];

    const escape = (val: string | number | null | undefined) => {
      if (val == null) return "";
      const s = String(val);
      return s.includes(",") || s.includes('"') || s.includes("\n")
        ? `"${s.replace(/"/g, '""')}"` : s;
    };

    const rows = reservations.map((r) => [
      escape(r.id),
      escape(r.share),
      escape(r.share_name),
      escape(r.booked_by_shareholder_name),
      escape(r.start_date),
      escape(r.end_date),
      escape(r.is_day_use ? "Day Use" : "Overnight"),
      escape(r.cabins.join(", ")),
      escape(r.guest_count),
      escape(r.base_cost?.toFixed(2)),
      escape(r.guest_fee?.toFixed(2)),
      escape(r.processing_fee?.toFixed(2)),
      escape(r.cost.toFixed(2)),
      escape(r.status),
      escape(r.booking_round),
      escape(r.created_at),
      escape(r.cancelled_at),
      escape(r.refund_amount?.toFixed(2)),
      escape(r.cancellation_reason),
    ].join(","));

    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `reservations-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const today = new Date().toISOString().split("T")[0]!;
  const filteredReservations = reservations.filter((r) => {
    // When searching, ignore time/status/cabin filters - search all reservations
    if (search) return matchesSearch(r, search);
    if (filter === "upcoming" && r.end_date < today) return false;
    if (filter === "past" && r.end_date >= today) return false;
    if (statusFilter !== "any" && r.status !== statusFilter) return false;
    if (cabinFilter !== "any" && !r.cabins.includes(cabinFilter)) return false;
    return true;
  });

  const isCancelled = (r: Reservation) => r.status === "cancelled" || r.status === "refunded";

  const getBookedByLabel = (reservation: Reservation) => {
    if (reservation.booked_by_shareholder_name) return reservation.booked_by_shareholder_name;
    if (reservation.booked_by_shareholder_id) return `Shareholder #${reservation.booked_by_shareholder_id}`;
    return "Legacy booking";
  };

  const renderResActions = (res: Reservation, guestLabel: string) => (
    <>
      <button
        className="action-btn edit-btn"
        onClick={() => setEditingGuestReservation(res)}
        disabled={isCancelled(res)}
      >
        {guestLabel}
      </button>
      <button
        className="action-btn edit-btn"
        onClick={() => setEditingReservation(res)}
      >
        Edit
      </button>
      {!isCancelled(res) ? (
        <>
          {res.status === "paid" && (
            <button
              className="action-btn refund-btn"
              onClick={() => void openRefundModal(res)}
              disabled={previewingRefund === res.id || refunding}
            >
              {previewingRefund === res.id ? "..." : "Refund"}
            </button>
          )}
          <button
            className="action-btn delete-btn"
            onClick={() => handleCancel(res.id)}
            disabled={cancelling === res.id}
          >
            {cancelling === res.id ? "..." : "Cancel"}
          </button>
        </>
      ) : null}
    </>
  );

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2>Reservations</h2>
        <div className="admin-section-header-actions">
          <div className="filter-tabs">
            <button
              className={`filter-tab ${filter === "upcoming" ? "active" : ""}`}
              onClick={() => setFilter("upcoming")}
            >
              Upcoming
            </button>
            <button
              className={`filter-tab ${filter === "past" ? "active" : ""}`}
              onClick={() => setFilter("past")}
            >
              Past
            </button>
            <button
              className={`filter-tab ${filter === "all" ? "active" : ""}`}
              onClick={() => setFilter("all")}
            >
              All
            </button>
          </div>
          <button
            className="action-btn export-btn"
            onClick={handleExport}
            disabled={reservations.length === 0}
            title="Export all reservations as CSV"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Export CSV
          </button>
        </div>
      </div>
      <div className="reservations-filters">
        <div className="reservations-search">
          <svg className="reservations-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className="form-input reservations-search-input"
            placeholder="Search by name, cabin, date, status..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              className="reservations-search-clear"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>
        <div className="filter-tabs">
          {(["any", "reserved", "unpaid", "paid", "cancelled", "refunded"] as const).map((s) => (
            <button
              key={s}
              className={`filter-tab${statusFilter === s ? " active" : ""}`}
              onClick={() => setStatusFilter(s)}
            >
              {s === "any" ? "Any Status" : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
        <div className="filter-tabs">
          {(["any", "pine", "cedar"] as const).map((c) => (
            <button
              key={c}
              className={`filter-tab${cabinFilter === c ? " active" : ""}`}
              onClick={() => setCabinFilter(c)}
            >
              {c === "any" ? "Any Cabin" : c.charAt(0).toUpperCase() + c.slice(1)}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="modal-error">{error}</div>}
      {guestEditMessage && <div className="modal-success">{guestEditMessage}</div>}
      <div className="admin-desktop-only admin-table-container">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Share</th>
                <th>Booked By</th>
                <th>Dates</th>
                <th>Cabins</th>
                <th>Additional Guests</th>
                <th>Cost</th>
                <th>Status <InfoTip text="Reserved = confirmed, Unpaid = awaiting payment, Paid = complete, Cancelled = cancelled, Refunded = cancelled with refund" /></th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredReservations.map((res) => (
                <tr key={res.id} className={isCancelled(res) ? "cancelled-row" : ""}>
                  <td>{res.id}</td>
                  <td>{res.share_name || res.share}</td>
                  <td>{getBookedByLabel(res)}</td>
                  <td className="dates-cell">
                    {res.is_day_use ? res.start_date : `${res.start_date} - ${res.end_date}`}
                  </td>
                  <td>
                    {res.cabins.map((cabin) => (
                      <span key={cabin} className={`cabin-badge ${cabin}`}>
                        {cabin}
                      </span>
                    ))}
                  </td>
                  <td>{res.guest_count}</td>
                  <td>
                    ${res.cost.toFixed(2)}
                    {res.status === "refunded" && res.refund_amount != null && (
                      <div className="refund-amount">-${res.refund_amount.toFixed(2)}</div>
                    )}
                  </td>
                  <td>
                    <span className={`badge badge-${res.status}`}>
                      {res.status}
                    </span>
                  </td>
                  <td className="actions-cell">
                    {renderResActions(res, "Edit Guests")}
                  </td>
                </tr>
              ))}
              {filteredReservations.length === 0 && (
                <tr>
                  <td colSpan={9} className="empty-row">
                    No reservations found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
      </div>
      <div className="admin-mobile-only">
        {filteredReservations.length === 0 ? (
          <div className="admin-mobile-empty">No reservations found</div>
        ) : (
          <div className="admin-mobile-compact-list">
            {filteredReservations.map((res) => (
              <AdminMobileRow
                key={res.id}
                muted={isCancelled(res)}
                eyebrow={`Reservation #${res.id}`}
                badge={<span className={`badge badge-${res.status}`}>{res.status}</span>}
                title={res.share_name || res.share}
                meta={[
                  `Booked by ${getBookedByLabel(res)}`,
                  res.is_day_use ? res.start_date : `${res.start_date} - ${res.end_date}`,
                  `${res.cabins.join(", ")} • ${res.guest_count} guests`,
                  `$${res.cost.toFixed(2)}${res.status === "refunded" && res.refund_amount != null ? ` • Refunded $${res.refund_amount.toFixed(2)}` : ""}`,
                ]}
                actions={renderResActions(res, "Guests")}
              />
            ))}
          </div>
        )}
      </div>
      {editingReservation && (
        <EditModal
          reservation={editingReservation}
          onClose={() => setEditingReservation(null)}
          onSave={handleSave}
        />
      )}
      {editingGuestReservation && (
        <GuestAdjustmentModal
          reservation={editingGuestReservation}
          onClose={() => setEditingGuestReservation(null)}
          onSaved={(result) => setGuestEditMessage(result.message)}
          previewGuestAdjustment={previewGuestAdjustment}
          startGuestAdjustmentCheckout={startGuestAdjustmentCheckout}
          applyGuestAdjustment={applyGuestAdjustment}
          refundGuestAdjustment={refundGuestAdjustment}
          isAdmin
        />
      )}
      {refundModal && (
        <RefundModal
          reservation={refundModal.reservation}
          preview={refundModal.preview}
          refunding={refunding}
          error={refundError}
          onClose={() => {
            setRefundModal(null);
            setRefundError(null);
          }}
          onConfirm={handleRefund}
        />
      )}
    </div>
  );
}
