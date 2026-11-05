import { useState, useMemo, useEffect, useRef } from "react";
import { useMultiMonthReservations } from "../hooks/useMultiMonthReservations";
import { useCalendarScroll } from "../hooks/useCalendarScroll";
import { useAppData } from "../context/AppDataContext";
import { CalendarMonth } from "./CalendarMonth";
import { CalendarLegend } from "./CalendarLegend";
import { BookingModal } from "./BookingModal";
import { BookingStatusBanner } from "./BookingStatusBanner";
import { DashboardStrip } from "./DashboardStrip";
import { getCabinName } from "../utils";
import {
  canUseFullyBookedDayAsCheckout,
  getBlockingReservations,
  isFullyBooked as getIsFullyBooked,
} from "../utils/calendarSelection";
import { getCalendarWindow } from "../utils/calendarWindow";
import type {
  CalendarDay as CalendarDayType,
  CalendarDayReservation,
  ReservationSegmentMeta,
  ReservationSegmentType,
} from "../types";

const MONTH_COUNT = 12;
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface CalendarProps {
  effectiveToday?: string;
}

export function Calendar({ effectiveToday }: CalendarProps) {
  const today = effectiveToday ? new Date(effectiveToday + "T00:00:00") : new Date();
  const baseYear = today.getFullYear();
  const baseMonth = today.getMonth() + 1; // 1-indexed
  const calendarWindow = useMemo(
    () => getCalendarWindow(baseYear, baseMonth, MONTH_COUNT),
    [baseMonth, baseYear]
  );

  const [startDate, setStartDate] = useState<string | null>(null);
  const [endDate, setEndDate] = useState<string | null>(null);
  const [showBookingModal, setShowBookingModal] = useState(false);
  const [selectedDayReservations, setSelectedDayReservations] = useState<CalendarDayReservation[] | null>(null);

  const { months, monthKeys, isLoading, error, refreshAll, checkAvailability } =
    useMultiMonthReservations(calendarWindow.startYear, calendarWindow.startMonth, calendarWindow.count);

  const {
    bookingStatus,
    bookingStatusLoading: statusLoading,
    refreshBookingStatus,
    cabins,
    cabinsError: cabinError,
    isViewer,
  } = useAppData();
  const previousEffectiveTodayRef = useRef(effectiveToday);
  const {
    calendarRef,
    monthListRef,
    stickyToolsShellRef,
    stickyToolsRef,
    isCalendarToolsPinned,
    scrollNavState,
    registerMonthAnchor,
    handleScrollToTop,
    handleScrollToCurrentMonth,
    handleScrollMonth,
  } = useCalendarScroll({
    isLoading,
    monthKeys,
    currentMonthKey: calendarWindow.currentMonthKey,
    layoutVersion: months,
  });

  useEffect(() => {
    document.documentElement.classList.add("calendar-scroll-page");
    return () => document.documentElement.classList.remove("calendar-scroll-page");
  }, []);

  useEffect(() => {
    if (previousEffectiveTodayRef.current === effectiveToday) return;
    previousEffectiveTodayRef.current = effectiveToday;
    refreshBookingStatus();
  }, [effectiveToday, refreshBookingStatus]);

  // Auto-refresh calendar on tab refocus
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        refreshBookingStatus();
        void refreshAll(true);
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [refreshAll, refreshBookingStatus]);

  const todayStr = useMemo(() => {
    if (effectiveToday) return effectiveToday;
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, "0");
    const d = String(today.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }, [effectiveToday]);

  const isSelectableDate = (dateStr: string): boolean => {
    return !isViewer && dateStr >= todayStr;
  };

  const isBookedDay = (day: { reservations: CalendarDayReservation[] }) => {
    return isFullyBooked(day);
  };

  const isFullyBooked = (day: { reservations: CalendarDayReservation[] }) => {
    return getIsFullyBooked(day, cabins.map((cabin) => cabin.cabin_id));
  };

  const isCheckoutSelectableDay = (day: CalendarDayType) => {
    return isFullyBooked(day) && canUseFullyBookedDayAsCheckout(startDate, endDate, day.date);
  };

  const handleDayClick = (day: CalendarDayType) => {
    const date = day.date;

    if (isFullyBooked(day) && !canUseFullyBookedDayAsCheckout(startDate, endDate, date)) {
      setSelectedDayReservations(getBlockingReservations(day));
      return;
    }

    if (!startDate || (startDate && endDate)) {
      setStartDate(date);
      setEndDate(null);
      setShowBookingModal(false);
    } else {
      if (date < startDate) {
        setEndDate(startDate);
        setStartDate(date);
      } else if (date === startDate) {
        setEndDate(date);
      } else {
        setEndDate(date);
      }
      setShowBookingModal(true);
    }
  };

  const handleCloseBookingModal = () => {
    setShowBookingModal(false);
    setStartDate(null);
    setEndDate(null);
  };

  const handleClearSelection = () => {
    setShowBookingModal(false);
    setStartDate(null);
    setEndDate(null);
  };

  const handleBookingSuccess = () => {
    handleCloseBookingModal();
    refreshBookingStatus();
  };

  const isInRange = (date: string) => {
    if (!startDate) return false;
    if (!endDate) return date === startDate;
    return date >= startDate && date <= endDate;
  };

  const reservationSegments = useMemo(() => {
    const daysInOrder: CalendarDayType[] = [];
    for (const { key } of monthKeys) {
      const monthData = months.get(key);
      if (!monthData) continue;
      daysInOrder.push(...monthData.days);
    }

    const defaultSegment: ReservationSegmentMeta = { segment: "single", showLabel: true };
    if (daysInOrder.length === 0) {
      return {
        getSegment: () => defaultSegment,
      };
    }

    const reservationPresenceByDate = new Map<string, Set<string>>();
    for (const day of daysInOrder) {
      const set = new Set<string>();
      for (const reservation of day.reservations) {
        for (const cabinId of reservation.cabins) {
          set.add(`${reservation.id}|${cabinId}`);
        }
      }
      reservationPresenceByDate.set(day.date, set);
    }

    const segmentByOccurrence = new Map<string, ReservationSegmentMeta>();
    for (let i = 0; i < daysInOrder.length; i++) {
      const day = daysInOrder[i];
      if (!day) continue;
      const currentSet = reservationPresenceByDate.get(day.date);
      if (!currentSet || currentSet.size === 0) continue;

      const prevDay = i > 0 ? daysInOrder[i - 1] : undefined;
      const nextDay = i < daysInOrder.length - 1 ? daysInOrder[i + 1] : undefined;
      const prevDate = prevDay?.date ?? null;
      const nextDate = nextDay?.date ?? null;
      const prevSet = prevDate ? reservationPresenceByDate.get(prevDate) : null;
      const nextSet = nextDate ? reservationPresenceByDate.get(nextDate) : null;

      for (const occurrenceKey of currentSet) {
        const hasPrev = prevSet?.has(occurrenceKey) ?? false;
        const hasNext = nextSet?.has(occurrenceKey) ?? false;

        let segment: ReservationSegmentType = "single";
        if (hasPrev && hasNext) segment = "middle";
        else if (!hasPrev && hasNext) segment = "start";
        else if (hasPrev && !hasNext) segment = "end";

        segmentByOccurrence.set(
          `${day.date}|${occurrenceKey}`,
          {
            segment,
            showLabel: !hasPrev,
          }
        );
      }
    }

    return {
      getSegment: (date: string, reservationId: number, cabinId: string): ReservationSegmentMeta => {
        return segmentByOccurrence.get(`${date}|${reservationId}|${cabinId}`) ?? defaultSegment;
      },
    };
  }, [monthKeys, months]);

  // Night count for selection hint
  const nightCount = useMemo(() => {
    if (!startDate) return 0;
    if (!endDate) return 0;
    const s = new Date(startDate + "T00:00:00");
    const e = new Date(endDate + "T00:00:00");
    return Math.round((e.getTime() - s.getTime()) / (1000 * 60 * 60 * 24));
  }, [startDate, endDate]);

  if (isLoading) {
    return (
      <div className="calendar calendar--journal loading">
        <div className="spinner" />
      </div>
    );
  }

  if (error) {
    return <div className="calendar calendar--journal calendar-error">{error}</div>;
  }

  if (cabinError) {
    return <div className="calendar calendar--journal calendar-error">{cabinError}</div>;
  }

  return (
    <div className="calendar calendar--journal" ref={calendarRef}>
      <div
        className={`calendar-scroll-rail calendar-scroll-rail--top${!scrollNavState.canScrollTop ? " at-page-top" : ""}`}
        aria-label="Calendar quick navigation"
      >
        {!scrollNavState.canScrollTop && (
          <div className="calendar-scroll-current-month-slot">
            <span className="calendar-scroll-btn-spacer" aria-hidden="true" />
            <button
              type="button"
              className="calendar-scroll-btn"
              onClick={handleScrollToCurrentMonth}
              aria-label="Go to current month"
              title="Go to current month"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 3V7" />
                <path d="M16 3V7" />
                <path d="M4 9H20" />
                <rect x="4" y="5" width="16" height="16" rx="2" />
              </svg>
              <span>Current Month</span>
            </button>
          </div>
        )}
        {scrollNavState.canScrollTop && (
          <button
            type="button"
            className="calendar-scroll-btn"
            onClick={handleScrollToTop}
            aria-label="Scroll to top"
            title="Scroll to top"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 11L12 4L19 11" />
              <path d="M12 5V20" />
            </svg>
            <span>Top</span>
          </button>
        )}
        {scrollNavState.canScrollPrev && (
          <button
            type="button"
            className="calendar-scroll-btn"
            onClick={() => handleScrollMonth(-1)}
            aria-label="Previous month"
            title="Previous month"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12L12 5L19 12" />
              <path d="M12 6V19" />
            </svg>
            <span>Prev Month</span>
          </button>
        )}
      </div>
      {scrollNavState.canScrollNext && (
        <div className="calendar-scroll-rail calendar-scroll-rail--bottom" aria-label="Calendar quick navigation">
          <button
            type="button"
            className="calendar-scroll-btn"
            onClick={() => handleScrollMonth(1)}
            aria-label="Next month"
            title="Next month"
          >
            <span>Next Month</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12L12 19L19 12" />
              <path d="M12 5V18" />
            </svg>
          </button>
        </div>
      )}

      <div data-tour="status-banner">
        <DashboardStrip status={bookingStatus} isLoading={statusLoading} effectiveToday={effectiveToday} />
        <BookingStatusBanner status={bookingStatus} isLoading={statusLoading} effectiveToday={effectiveToday} />
      </div>

      <div className="calendar-main">
        <div
          className={`calendar-sticky-tools-shell${isCalendarToolsPinned ? " is-pinned" : ""}`}
          ref={stickyToolsShellRef}
        >
          <div className="calendar-sticky-tools" ref={stickyToolsRef}>
            <div className="calendar-legend-wrap">
              <CalendarLegend cabins={cabins} />
              {startDate && (
                <div className="calendar-selection-hint" role="status" aria-live="polite">
                  {!endDate ? (
                    <>
                      <span>Select checkout date. Select same day for day use.</span>
                      <button
                        type="button"
                        className="calendar-selection-clear"
                        onClick={handleClearSelection}
                        aria-label="Clear selected check-in date"
                      >
                        &times;
                      </button>
                    </>
                  ) : !showBookingModal && nightCount > 0 ? (
                    <>
                      <span>{nightCount} night{nightCount !== 1 ? "s" : ""} selected</span>
                      <button
                        type="button"
                        className="calendar-selection-clear"
                        onClick={handleClearSelection}
                        aria-label="Clear selection"
                      >
                        &times;
                      </button>
                    </>
                  ) : null}
                </div>
              )}
            </div>

            <div className="calendar-weekdays calendar-weekdays--global">
              {WEEKDAYS.map((day) => (
                <div key={day} className="weekday">
                  {day}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="calendar-month-pair" ref={monthListRef}>
          {monthKeys.map(({ year, month, key }) => {
            const monthData = months.get(key);
            if (!monthData) return null;

            return (
              <div
                key={key}
                ref={(element) => registerMonthAnchor(key, element)}
                className="calendar-month-anchor"
              >
                <CalendarMonth
                  year={year}
                  month={month}
                  days={monthData.days}
                  todayStr={todayStr}
                  startDate={startDate}
                  endDate={endDate}
                  isInRange={isInRange}
                  isSelectable={isSelectableDate}
                  isFullyBooked={isFullyBooked}
                  isBookedDay={isBookedDay}
                  isCheckoutSelectableDay={isCheckoutSelectableDay}
                  onDayClick={handleDayClick}
                  getReservationSegment={reservationSegments.getSegment}
                  cabins={cabins}
                  showWeekdays={false}
                />
              </div>
            );
          })}
        </div>
      </div>

      {showBookingModal && startDate && endDate && (
        <BookingModal
          startDate={startDate}
          endDate={endDate}
          cabins={cabins}
          bookingStatus={bookingStatus}
          onClose={handleCloseBookingModal}
          onSuccess={handleBookingSuccess}
          checkAvailability={checkAvailability}
        />
      )}

      {selectedDayReservations && (
        <div className="modal-overlay" onClick={() => setSelectedDayReservations(null)}>
          <div className="modal reservation-details" onClick={(e) => e.stopPropagation()}>
            <h3>Fully Booked</h3>
            {selectedDayReservations.map((r) => (
              <div key={r.id} className="fully-booked-entry">
                <p>
                  <strong>{r.cabins.map((c) => getCabinName(cabins, c)).join(", ")}:</strong>{" "}
                  {r.calendar_display_name || r.share_name || r.share}{r.guest_count > 0 ? ` (+${r.guest_count} additional guest${r.guest_count === 1 ? '' : 's'})` : ''}
                  {" "}<span className="reservation-type-tag">{r.is_day_use ? "Day Use" : "Overnight"}</span>
                  {r.status === "unpaid" && (
                    <span className="reservation-type-tag reservation-payment-tag">Awaiting payment</span>
                  )}
                </p>
              </div>
            ))}
            <div className="modal-actions">
              <button onClick={() => setSelectedDayReservations(null)} className="cancel-btn">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
