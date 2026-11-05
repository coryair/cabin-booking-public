import type { BookingStatus } from "../types";
import { formatDate, nextPhaseText, roundLabel } from "../utils";

interface DashboardStripProps {
  status: BookingStatus | null;
  isLoading: boolean;
  effectiveToday?: string;
}

function shortRoundLabel(round: string): string {
  switch (round) {
    case "round_1": return "Round 1";
    case "round_2": return "Round 2";
    case "round_3": return "Round 3";
    default: return roundLabel(round);
  }
}

function stripBorderClass(status: BookingStatus): string {
  if (status.can_book) return "strip-border-active";
  return "strip-border-default";
}

export function DashboardStrip({ status, isLoading, effectiveToday }: DashboardStripProps) {
  if (isLoading || !status) return null;

  // Only show during rounds and between-rounds
  const isRound = ["round_1", "round_2", "round_3"].includes(status.current_round);
  if (!isRound && status.current_round !== "between_rounds") return null;

  const showBudgetAndPriority = isRound;
  const borderClass = stripBorderClass(status);
  const nextPhase = nextPhaseText(status, effectiveToday);

  // Section B content
  const renderBookingWindow = () => {
    if (isRound) {
      if (status.now_booking_share_name) {
        return (
          <>
            <span className="strip-section-label">Now Booking</span>
            <span className="strip-window-booking">{status.now_booking_share_name}</span>
          </>
        );
      }
      if (nextPhase) {
        return <span className="strip-window-next">{nextPhase}</span>;
      }
      return <span className="strip-window-next">Waiting for your window</span>;
    }

    // between_rounds
    if (nextPhase) {
      return <span className="strip-window-next">{nextPhase}</span>;
    }
    return <span className="strip-window-next">Next round coming soon</span>;
  };

  // Section C - Night Budget
  const renderNightBudget = () => {
    if (!showBudgetAndPriority || status.season_max_nights <= 0) return null;
    const used = status.nights_used;
    const max = status.season_max_nights;
    const lowBudget = (max - used) <= 4;

    return (
      <div className="strip-section strip-budget">
        <span className="strip-section-label">Prime Season Nights</span>
        <span className={`strip-budget-count${lowBudget ? " strip-budget-low" : ""}`}>
          {used}/{max}
        </span>
      </div>
    );
  };

  // Section D - Priority Position
  const renderPriority = () => {
    if (!showBudgetAndPriority || status.priority == null || status.total_shares == null) return null;
    return (
      <div className="strip-section strip-priority">
        <span className="strip-section-label">Priority</span>
        <span className="strip-priority-label">{status.priority}/{status.total_shares}</span>
      </div>
    );
  };

  return (
    <div className={`dashboard-strip ${borderClass}`}>
      {/* Round Label */}
      <div className="strip-section strip-round">
        <span className="strip-round-label">{roundLabel(status.current_round)}</span>
        {isRound && status.window_start && status.window_end && (
          <span className="strip-round-window">
            Your window: {formatDate(status.window_start)} – {formatDate(status.window_end)}
          </span>
        )}
      </div>

      <div className="strip-divider" />

      {/* Booking Window */}
      <div className="strip-section strip-status">
        {renderBookingWindow()}
      </div>

      {showBudgetAndPriority && (
        <>
          <div className="strip-divider" />
          <div className="strip-section strip-reservations">
            <span className="strip-section-label">{shortRoundLabel(status.current_round)} Reservations</span>
            <span className="strip-reservations-label">{status.round_reservations}/{status.round_max_reservations}</span>
          </div>
          {status.round_max_nights != null && (
            <>
              <div className="strip-divider" />
              <div className="strip-section strip-round-nights">
                <span className="strip-section-label">{shortRoundLabel(status.current_round)} Nights</span>
                <span className="strip-round-nights-label">{status.round_nights}/{status.round_max_nights}</span>
              </div>
            </>
          )}
          <div className="strip-divider" />
          {renderNightBudget()}
          <div className="strip-divider" />
          {renderPriority()}
        </>
      )}
    </div>
  );
}
