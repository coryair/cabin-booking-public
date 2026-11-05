import { useMemo, useState } from "react";
import type { Reservation, CabinType } from "../../types";
import { formatDate, nightCount } from "../../utils";
import { useAdminData } from "../../hooks/useAdminData";
import { reservationsApi } from "../../api/reservations";

type PaymentEmailState = {
  type: "success" | "error";
  message: string;
};

interface OverviewAdminProps {
  canSendPaymentEmails?: boolean;
}

export function OverviewAdmin({ canSendPaymentEmails = false }: OverviewAdminProps) {
  const { reservations, season, active, loading, error } = useAdminData();
  const [sendingPaymentEmailId, setSendingPaymentEmailId] = useState<number | null>(null);
  const [paymentEmailStates, setPaymentEmailStates] = useState<Record<number, PaymentEmailState>>({});

  const today = new Date().toISOString().slice(0, 10);
  const yearStart = season ? `${season.year}-01-01` : null;
  const yearEnd = season ? `${season.year + 1}-01-01` : null;

  const yearReservations = useMemo(() => {
    if (!yearStart || !yearEnd) return reservations;
    return reservations.filter(
      (r) => r.start_date < yearEnd && r.end_date > yearStart
    );
  }, [reservations, yearEnd, yearStart]);

  const yearActive = useMemo(() => {
    if (!yearStart || !yearEnd) return active;
    return active.filter(
      (r) => r.start_date < yearEnd && r.end_date > yearStart
    );
  }, [active, yearEnd, yearStart]);

  const atCabin = useMemo(
    () => yearActive.filter((r) => r.start_date <= today && r.end_date > today),
    [yearActive, today]
  );

  const upcoming = useMemo(
    () =>
      yearActive
        .filter((r) => r.start_date > today)
        .sort((a, b) => a.start_date.localeCompare(b.start_date))
        .slice(0, 5),
    [yearActive, today]
  );

  const unpaid = useMemo(
    () => yearActive.filter((r) => r.status === "unpaid"),
    [yearActive]
  );

  const totals = useMemo(() => {
    const paidRevenue = yearActive
      .filter((r) => r.status === "paid")
      .reduce((sum, r) => sum + r.cost, 0);
    const pendingRevenue = yearActive
      .filter((r) => r.status !== "paid")
      .reduce((sum, r) => sum + r.cost, 0);
    const totalNights = yearActive.reduce((sum, r) => sum + nightCount(r), 0);
    return { paidRevenue, pendingRevenue, totalNights, totalReservations: yearActive.length };
  }, [yearActive]);

  const recent = useMemo(() => {
    return [...yearReservations]
      .filter((r) => r.created_at)
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .slice(0, 5);
  }, [yearReservations]);

  const sendPaymentEmail = async (reservation: Reservation) => {
    setSendingPaymentEmailId(reservation.id);
    setPaymentEmailStates((current) => {
      const next = { ...current };
      delete next[reservation.id];
      return next;
    });

    try {
      const data = await reservationsApi.sendPaymentEmail(reservation.id);

      setPaymentEmailStates((current) => ({
        ...current,
        [reservation.id]: {
          type: "success",
          message: `Sent to ${data.booker_name || reservation.booked_by_shareholder_name || "booker"}`,
        },
      }));
    } catch (err) {
      setPaymentEmailStates((current) => ({
        ...current,
        [reservation.id]: {
          type: "error",
          message: err instanceof Error ? err.message : "Failed to send payment email",
        },
      }));
    } finally {
      setSendingPaymentEmailId(null);
    }
  };

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return <div className="admin-section admin-error">{error}</div>;
  }

  return (
    <div className="admin-section overview-section">
      <div className="admin-section-header">
        <h2>Dispatch{season ? ` - ${season.year}` : ""}</h2>
        <span className="overview-date">
          {new Date().toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
            year: "numeric",
          })}
        </span>
      </div>

      {/* --- AT THE CABIN / UPCOMING --- */}
      <div className="overview-grid">
        <div className="overview-panel">
          <h3 className="overview-panel-label">At the Cabin</h3>
          {atCabin.length === 0 ? (
            <p className="overview-empty">No one is at the cabin right now</p>
          ) : (
            <div className="overview-entries">
              {atCabin.map((r) => (
                <ReservationRow key={r.id} reservation={r} showStatus={false} />
              ))}
            </div>
          )}
        </div>
        <div className="overview-panel">
          <h3 className="overview-panel-label">Next Arrivals</h3>
          {upcoming.length === 0 ? (
            <p className="overview-empty">No upcoming reservations</p>
          ) : (
            <div className="overview-entries">
              {upcoming.map((r) => (
                <ReservationRow key={r.id} reservation={r} showStatus={false} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* --- NEEDS ATTENTION --- */}
      {unpaid.length > 0 && (
        <div className="overview-panel overview-attention">
          <h3 className="overview-panel-label">
            Needs Attention
            <span className="overview-attention-count">{unpaid.length}</span>
          </h3>
          <div className="overview-entries">
            {unpaid.map((r) => (
              <ReservationRow
                key={r.id}
                reservation={r}
                showStatus
                paymentEmailAction={canSendPaymentEmails && r.booked_by_shareholder_id ? {
                  isSending: sendingPaymentEmailId === r.id,
                  disabled: sendingPaymentEmailId !== null,
                  state: paymentEmailStates[r.id],
                  onSend: () => void sendPaymentEmail(r),
                } : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* --- SEASON TOTALS --- */}
      <div className="overview-totals">
        <div className="overview-total-item">
          <span className="overview-total-value">{totals.totalReservations}</span>
          <span className="overview-total-label">Reservations</span>
        </div>
        <div className="overview-total-item">
          <span className="overview-total-value">{totals.totalNights}</span>
          <span className="overview-total-label">Nights Booked</span>
        </div>
        <div className="overview-total-item">
          <span className="overview-total-value overview-total-paid">
            ${totals.paidRevenue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </span>
          <span className="overview-total-label">Collected</span>
        </div>
        {totals.pendingRevenue > 0 && (
          <div className="overview-total-item">
            <span className="overview-total-value overview-total-pending">
              ${totals.pendingRevenue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </span>
            <span className="overview-total-label">Pending</span>
          </div>
        )}
      </div>

      {/* --- RECENT ACTIVITY --- */}
      {recent.length > 0 && (
        <div className="overview-panel">
          <h3 className="overview-panel-label">Recent Activity</h3>
          <div className="overview-entries">
            {recent.map((r) => (
              <ReservationRow key={r.id} reservation={r} showStatus showCreated />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --- sub-components ---

function CabinChips({ cabins }: { cabins: CabinType[] }) {
  return (
    <span className="overview-cabin-chips">
      {cabins.map((c) => (
        <span key={c} className={`cabin-indicator ${c}`} title={c} />
      ))}
    </span>
  );
}

function ReservationRow({
  reservation: r,
  showStatus,
  showCreated,
  paymentEmailAction,
}: {
  reservation: Reservation;
  showStatus: boolean;
  showCreated?: boolean;
  paymentEmailAction?: {
    isSending: boolean;
    disabled: boolean;
    state?: PaymentEmailState;
    onSend: () => void;
  };
}) {
  const nights = nightCount(r);
  const dateRange = r.is_day_use
    ? formatDate(r.start_date)
    : `${formatDate(r.start_date)} – ${formatDate(r.end_date)}`;
  const bookerName = r.booked_by_shareholder_name || "booker";

  return (
    <div className={`overview-entry${r.status === "cancelled" || r.status === "refunded" ? " is-muted" : ""}`}>
      <CabinChips cabins={r.cabins} />
      <div className="overview-entry-body">
        <span className="overview-entry-who">
          {r.share_name || r.share}
          {r.booked_by_shareholder_name && r.booked_by_shareholder_name !== (r.share_name || r.share) && (
            <span className="overview-entry-booker"> · booked by {r.booked_by_shareholder_name}</span>
          )}
        </span>
        <span className="overview-entry-when">
          {dateRange}
          {!r.is_day_use && <span className="overview-entry-nights"> · {nights}n</span>}
        </span>
      </div>
      <div className="overview-entry-end">
        {showStatus && <span className={`badge badge-${r.status}`}>{r.status}</span>}
        {showCreated && r.created_at && (
          <span className="overview-entry-created">
            {formatDate(r.created_at.slice(0, 10))}
          </span>
        )}
        <span className="overview-entry-cost">${r.cost.toFixed(0)}</span>
      </div>
      {paymentEmailAction && (
        <div className="overview-entry-action">
          <button
            type="button"
            className="overview-payment-email-btn"
            onClick={paymentEmailAction.onSend}
            disabled={paymentEmailAction.disabled}
          >
            {paymentEmailAction.isSending ? "Sending..." : `Send payment email to ${bookerName}`}
          </button>
          {paymentEmailAction.state && (
            <span className={`overview-payment-email-state ${paymentEmailAction.state.type}`}>
              {paymentEmailAction.state.message}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
