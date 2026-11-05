import { describe, expect, test } from "bun:test";

import { scrollCalendarMonthIntoContainer } from "./scrollCalendarMonth";

function createElementStub(top: number) {
  return {
    getBoundingClientRect: () => ({ top }),
  };
}

describe("scrollCalendarMonthIntoContainer", () => {
  test("scrolls the month list without delegating to page-level scrollIntoView", () => {
    const container = {
      scrollTop: 24,
      getBoundingClientRect: () => ({ top: 100 }),
    };
    const target = {
      ...createElementStub(340),
      scrollIntoView: () => {
        throw new Error("scrollIntoView should not be called");
      },
    };

    scrollCalendarMonthIntoContainer(container, target);

    expect(container.scrollTop).toBe(264);
  });
});
