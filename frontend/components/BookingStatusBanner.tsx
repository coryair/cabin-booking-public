import { useEffect, useState, type KeyboardEvent } from "react";
import type { BookingStatus } from "../types";
import { formatDate, nextPhaseText, roundLabel } from "../utils";

interface BookingStatusBannerProps {
  status: BookingStatus | null;
  isLoading: boolean;
  effectiveToday?: string;
}

export function BookingStatusBanner({ status, isLoading, effectiveToday }: BookingStatusBannerProps) {
  const [showRoundDetails, setShowRoundDetails] = useState(false);
  const [showCompactDetails, setShowCompactDetails] = useState(false);
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(min-width: 769px)").matches : false
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mediaQuery = window.matchMedia("(min-width: 769px)");
    const handleChange = (event: MediaQueryListEvent) => {
      setIsDesktop(event.matches);
    };

    setIsDesktop(mediaQuery.matches);
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  if (isLoading || !status) return null;

  const isRound = ["round_1", "round_2", "round_3"].includes(status.current_round);

  const showNights = status.season_max_nights > 0 && isRound;
  const nextPhase = nextPhaseText(status, effectiveToday);
  const isOffseason = status.current_round === "offseason";
  const isOpen = status.current_round === "open";
  const isCompact = isOffseason || isOpen;
  const isCompactCollapsible = isCompact && !isDesktop;
  const showCompactInlineDetails = isCompact && (isDesktop || showCompactDetails);
  const showPrimeLock = isOffseason &&
    status.prime_season_start && status.prime_season_end;
  const handleCompactKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!isCompactCollapsible) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setShowCompactDetails((current) => !current);
    }
  };
  const handleCompactClick = () => {
    if (!isCompactCollapsible) return;
    setShowCompactDetails((current) => !current);
  };
  return (
    <div
      className={`booking-status-banner ${status.can_book ? "can-book" : "cannot-book"}${isCompact ? " offseason-compact" : ""}`}
      role={isCompactCollapsible ? "button" : undefined}
      tabIndex={isCompactCollapsible ? 0 : undefined}
      aria-expanded={isCompactCollapsible ? showCompactDetails : undefined}
      onClick={isCompactCollapsible ? handleCompactClick : undefined}
      onKeyDown={isCompactCollapsible ? handleCompactKeyDown : undefined}
    >
      {isRound ? (
        <div className={`banner-round${showRoundDetails ? " banner-round-open" : ""}`}>
          <button
            className="guide-round-toggle"
            onClick={() => setShowRoundDetails(d => !d)}
            aria-expanded={showRoundDetails}
          >
            <div className="guide-round-header">
              <span className="guide-round-label">
                {roundLabel(status.current_round)}
              </span>
              <span className="guide-round-hint">
                – {showRoundDetails ? "tap to collapse" : "tap for details"}
              </span>
              <svg className={`guide-round-chevron${showRoundDetails ? " open" : ""}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </div>
            <div className="banner-round-summary guide-round-details">
              {(() => {
                const parts: string[] = [];
                if (status.now_booking_share_name) parts.push(`Now booking: ${status.now_booking_share_name}`);
                if (status.priority != null && status.total_shares != null) parts.push(`Priority ${status.priority} of ${status.total_shares}`);
                if (showNights) parts.push(`${status.nights_used}/${status.season_max_nights} nights`);
                return parts.map((text, i) => (
                  <span key={i}>
                    {i > 0 && <span className="guide-detail-sep"> &middot; </span>}
                    {text}
                  </span>
                ));
              })()}
            </div>
          </button>

          <div className="banner-round-expanded booking-status-details">
            {status.priority != null && status.total_shares != null && (
              <span className="booking-status-priority">
                Priority {status.priority} of {status.total_shares}
              </span>
            )}
            {status.now_booking_share_name && (
              <span className="booking-status-now-booking">
                Now booking: {status.now_booking_share_name}
              </span>
            )}
            {nextPhase && (
              <span className="booking-status-next-phase">{nextPhase}</span>
            )}
            {showNights && (
              <span className="booking-status-nights">
                {status.nights_used} / {status.season_max_nights} priority round nights used
              </span>
            )}
            {!status.can_book && status.reason && (
              <div className="booking-status-reason">{status.reason}</div>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="booking-status-round">
            <span className="booking-status-round-label">
              {roundLabel(status.current_round)}
            </span>
            {isCompactCollapsible && (
              <span className="booking-status-offseason-toggle">
                {showCompactDetails ? "Hide details" : "Show details"}
              </span>
            )}
          </div>

          {showPrimeLock && !isCompact && (
            <div className="booking-status-prime-lock">
              Prime season ({formatDate(status.prime_season_start!)} &ndash; {formatDate(status.prime_season_end!)}) dates locked until rounds begin
            </div>
          )}

          {!isCompact && (
            <div className="booking-status-details">
              {nextPhase && (
                <span className="booking-status-next-phase">{nextPhase}</span>
              )}
            </div>
          )}

          {showCompactInlineDetails && (
            <div className="booking-status-inline-details">
              {showPrimeLock && (
                <div className="booking-status-prime-lock">
                  Prime season ({formatDate(status.prime_season_start!)} &ndash; {formatDate(status.prime_season_end!)}) dates locked until rounds begin
                </div>
              )}
              {isOpen && (
                <div className="booking-status-next-phase">Can book up to 30 days in advance</div>
              )}
              {nextPhase && (
                <div className="booking-status-next-phase">{nextPhase}</div>
              )}
            </div>
          )}

          {!status.can_book && status.reason && (
            <div className="booking-status-reason">{status.reason}</div>
          )}
        </>
      )}
    </div>
  );
}
