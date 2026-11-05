import type {
  CalendarDay as CalendarDayType,
  Cabin,
  ReservationSegmentMeta,
} from "../types";

interface CalendarDayProps {
  day: CalendarDayType;
  isToday: boolean;
  isSelected: boolean;
  isInRange: boolean;
  isSelectable: boolean;
  isFullyBooked: boolean;
  isBooked: boolean;
  isCheckoutSelectable: boolean;
  onClick: () => void;
  getReservationSegment: (date: string, reservationId: number, cabinId: string) => ReservationSegmentMeta;
  cabins: Cabin[];
}

export function CalendarDay({
  day,
  isToday,
  isSelected,
  isInRange,
  isSelectable,
  isFullyBooked,
  isBooked,
  isCheckoutSelectable,
  onClick,
  getReservationSegment,
  cabins = [],
}: CalendarDayProps) {
  const dayNumber = day.day;
  const orderedCabins = [...cabins].sort((a, b) => {
    const rank = (id: string) => {
      if (id === "pine") return 0;
      if (id === "cedar") return 1;
      return 2;
    };
    const rankDiff = rank(a.cabin_id) - rank(b.cabin_id);
    if (rankDiff !== 0) return rankDiff;
    return a.cabin_name.localeCompare(b.cabin_name);
  });

  const reservedCabinIds = new Set<string>();
  for (const r of day.reservations) {
    for (const cabinId of r.cabins) {
      reservedCabinIds.add(cabinId);
    }
  }

  const getReservationsForCabin = (cabinId: string) => {
    return day.reservations.filter((r) => (r.cabins as string[]).includes(cabinId));
  };

  const classNames = [
    "calendar-day",
    isToday ? "today" : "",
    isSelected ? "selected" : "",
    isInRange ? "in-range" : "",
    !isSelectable ? "disabled" : "",
    isBooked ? "booked" : "",
    isFullyBooked && isSelectable ? "fully-booked" : "",
    isCheckoutSelectable ? "checkout-selectable" : "",
    ...Array.from(reservedCabinIds).map((id) => `has-${id}`),
  ]
    .filter((c) => c)
    .join(" ");

  return (
    <div className={classNames} onClick={isSelectable && (!isBooked || isCheckoutSelectable) ? onClick : undefined}>
      <span className="day-number">{dayNumber}</span>

      <div className="day-bars">
        {orderedCabins.map((cabin) => {
          const reservations = getReservationsForCabin(cabin.cabin_id);
          return (
            <div key={cabin.cabin_id} className={`day-cabin-lane day-cabin-lane--${cabin.cabin_id}`}>
              {(reservations.length > 1
                ? [...reservations].sort((a, b) => {
                    const segA = getReservationSegment(day.date, a.id, cabin.cabin_id);
                    const segB = getReservationSegment(day.date, b.id, cabin.cabin_id);
                    const pri = (s: string) => (s === "end" || s === "middle") ? 0 : 1;
                    return pri(segA.segment) - pri(segB.segment);
                  })
                : reservations
              ).map((reservation) => {
                const segment = getReservationSegment(day.date, reservation.id, cabin.cabin_id);
                const barClasses = [
                  "day-bar",
                  cabin.cabin_id,
                  reservation.status === "unpaid" ? "unpaid" : "",
                  reservation.is_checkout ? "checkout" : "",
                  reservation.is_day_use ? "day-use" : "",
                  `segment-${segment.segment}`,
                ].filter(Boolean).join(" ");

                const shareName = reservation.calendar_display_name || reservation.share_name || reservation.share;
                const label = reservation.status === "unpaid" ? `${shareName} - payment due` : shareName;

                return (
                  <div
                    key={`${cabin.cabin_id}-${reservation.id}`}
                    className={barClasses}
                    style={isFullyBooked ? { pointerEvents: "none" } : undefined}
                    title={label}
                  >
                    {shareName && segment.showLabel && <span className="day-bar-label">{label}</span>}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
