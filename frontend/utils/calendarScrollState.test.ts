import { describe, expect, it } from "bun:test";
import { getCalendarScrollNavState, getFocusedMonthIndex } from "./calendarScrollState";

const months = [
  { key: "2026-07", top: 100, bottom: 700 },
  { key: "2026-08", top: 700, bottom: 1300 },
  { key: "2026-09", top: 1300, bottom: 1900 },
];

describe("calendar scroll state", () => {
  it("finds the focused month from cached page bounds", () => {
    expect(getFocusedMonthIndex(months, 0, 120)).toBe(0);
    expect(getFocusedMonthIndex(months, 650, 120)).toBe(1);
    expect(getFocusedMonthIndex(months, 1800, 120)).toBe(2);
  });

  it("shows only valid desktop navigation actions", () => {
    expect(getCalendarScrollNavState({
      isDesktop: true,
      scrollY: 650,
      viewportHeight: 800,
      documentHeight: 2400,
      focusedIndex: 1,
      monthCount: 3,
    })).toEqual({ canScrollTop: true, canScrollPrev: true, canScrollNext: true });
  });

  it("hides rail navigation on mobile and at the page top", () => {
    expect(getCalendarScrollNavState({
      isDesktop: false,
      scrollY: 500,
      viewportHeight: 800,
      documentHeight: 2400,
      focusedIndex: 1,
      monthCount: 3,
    })).toEqual({ canScrollTop: false, canScrollPrev: false, canScrollNext: false });
    expect(getCalendarScrollNavState({
      isDesktop: true,
      scrollY: 0,
      viewportHeight: 800,
      documentHeight: 2400,
      focusedIndex: 0,
      monthCount: 3,
    })).toEqual({ canScrollTop: false, canScrollPrev: false, canScrollNext: false });
  });
});
