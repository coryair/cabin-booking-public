import { describe, expect, test } from "bun:test";
import { shouldFinishCalendarLoading } from "./useMultiMonthReservations";

describe("calendar request loading ownership", () => {
  test("finishes loading for an active foreground request", () => {
    expect(shouldFinishCalendarLoading(false, { aborted: false })).toBe(true);
  });

  test("does not finish loading for an aborted request", () => {
    expect(shouldFinishCalendarLoading(false, { aborted: true })).toBe(false);
  });

  test("does not change loading state for a silent refresh", () => {
    expect(shouldFinishCalendarLoading(true, { aborted: false })).toBe(false);
  });
});
