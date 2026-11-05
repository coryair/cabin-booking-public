export interface MonthBounds {
  key: string;
  top: number;
  bottom: number;
}
export interface CalendarScrollNavState {
  canScrollTop: boolean;
  canScrollPrev: boolean;
  canScrollNext: boolean;
}

export function getFocusedMonthIndex(
  bounds: MonthBounds[],
  scrollY: number,
  stickyOffset: number,
): number {
  if (bounds.length === 0) return -1;
  const focusLine = scrollY + stickyOffset + 16;
  const visibleIndex = bounds.findIndex((month) => month.bottom > focusLine);
  return visibleIndex >= 0 ? visibleIndex : bounds.length - 1;
}

export function getCalendarScrollNavState(input: {
  isDesktop: boolean;
  scrollY: number;
  viewportHeight: number;
  documentHeight: number;
  focusedIndex: number;
  monthCount: number;
}): CalendarScrollNavState {
  if (!input.isDesktop) {
    return { canScrollTop: false, canScrollPrev: false, canScrollNext: false };
  }

  const isAtTop = input.scrollY <= 2;
  const isAtBottom = input.scrollY + input.viewportHeight >= input.documentHeight - 2;
  return {
    canScrollTop: !isAtTop,
    canScrollPrev: !isAtTop && input.focusedIndex > 0,
    canScrollNext:
      !isAtTop
      && !isAtBottom
      && input.focusedIndex >= 0
      && input.focusedIndex < input.monthCount - 1,
  };
}
