import { describe, expect, test } from "bun:test";

import { getCalendarWindow } from "./calendarWindow";

describe("getCalendarWindow", () => {
  test("loads from January through the existing forward horizon", () => {
    expect(getCalendarWindow(2026, 5, 12)).toEqual({
      startYear: 2026,
      startMonth: 1,
      count: 16,
      currentMonthKey: "2026-05",
    });
  });

  test("supports December without shortening the forward horizon", () => {
    expect(getCalendarWindow(2026, 12, 12)).toEqual({
      startYear: 2026,
      startMonth: 1,
      count: 23,
      currentMonthKey: "2026-12",
    });
  });
});
