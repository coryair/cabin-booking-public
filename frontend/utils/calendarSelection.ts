import type { CalendarDay, CalendarDayReservation } from "../types";

type CalendarDayLike = Pick<CalendarDay, "reservations">;

export function getBlockingReservations(day: CalendarDayLike): CalendarDayReservation[] {
  return day.reservations.filter((reservation) => !reservation.is_checkout);
}

export function isFullyBooked(day: CalendarDayLike, cabinIds: string[]): boolean {
  if (cabinIds.length === 0) return false;

  const activeCabins = new Set(cabinIds);
  const reservedCabins = new Set<string>();

  for (const reservation of getBlockingReservations(day)) {
    for (const cabinId of reservation.cabins) {
      if (activeCabins.has(cabinId)) {
        reservedCabins.add(cabinId);
      }
    }
  }

  return reservedCabins.size >= activeCabins.size;
}

export function canUseFullyBookedDayAsCheckout(
  startDate: string | null,
  endDate: string | null,
  date: string,
): boolean {
  return startDate !== null && endDate === null && date > startDate;
}
