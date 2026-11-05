import { describe, expect, test } from "bun:test";

import type { CalendarDay, CalendarDayReservation, CabinType } from "../types";
import {
  canUseFullyBookedDayAsCheckout,
  getBlockingReservations,
  isFullyBooked,
} from "./calendarSelection";

const reservation = (
  id: number,
  cabins: CabinType[],
  isCheckout = false,
): CalendarDayReservation => ({
  id,
  share: `share-${id}`,
  cabins,
  guest_count: 0,
  is_day_use: false,
  status: "paid",
  is_checkout: isCheckout,
});

const calendarDay = (
  date: string,
  reservations: CalendarDayReservation[],
): CalendarDay => ({
  date,
  day: Number(date.slice(-2)),
  reservations,
});

describe("calendar selection helpers", () => {
  test("allows a fully booked day to complete an in-progress range as checkout", () => {
    expect(canUseFullyBookedDayAsCheckout("2026-05-20", null, "2026-05-21")).toBe(true);
  });

  test("does not allow a fully booked day to start a new range", () => {
    expect(canUseFullyBookedDayAsCheckout(null, null, "2026-05-21")).toBe(false);
  });

  test("does not allow the selected start date itself as a fully booked checkout date", () => {
    expect(canUseFullyBookedDayAsCheckout("2026-05-21", null, "2026-05-21")).toBe(false);
  });

  test("does not allow a date before the selected start date as a fully booked checkout date", () => {
    expect(canUseFullyBookedDayAsCheckout("2026-05-21", null, "2026-05-20")).toBe(false);
  });

  test("does not allow a fully booked checkout date after the range is already complete", () => {
    expect(canUseFullyBookedDayAsCheckout("2026-05-20", "2026-05-21", "2026-05-22")).toBe(false);
  });

  test("counts only non-checkout reservations as blocking full-day availability", () => {
    const day = calendarDay("2026-05-21", [
      reservation(1, ["pine"], true),
      reservation(2, ["cedar"], true),
    ]);

    expect(getBlockingReservations(day)).toEqual([]);
    expect(isFullyBooked(day, ["pine", "cedar"])).toBe(false);
  });

  test("reports fully booked when blocking reservations cover every cabin", () => {
    const day = calendarDay("2026-05-21", [
      reservation(1, ["pine"]),
      reservation(2, ["cedar"]),
    ]);

    expect(isFullyBooked(day, ["pine", "cedar"])).toBe(true);
  });
});
