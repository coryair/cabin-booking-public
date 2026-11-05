import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCalendarScrollNavState,
  getFocusedMonthIndex,
  type CalendarScrollNavState,
  type MonthBounds,
} from "../utils/calendarScrollState";
import { scrollCalendarMonthIntoContainer } from "../utils/scrollCalendarMonth";

interface MonthKey {
  key: string;
}

interface UseCalendarScrollOptions {
  isLoading: boolean;
  monthKeys: MonthKey[];
  currentMonthKey: string;
  layoutVersion: unknown;
}

interface LayoutMetrics {
  isDesktop: boolean;
  headerHeight: number;
  toolsHeight: number;
  pinStart: number;
  months: MonthBounds[];
}

const EMPTY_METRICS: LayoutMetrics = {
  isDesktop: false,
  headerHeight: 0,
  toolsHeight: 0,
  pinStart: 0,
  months: [],
};

const EMPTY_NAV: CalendarScrollNavState = {
  canScrollTop: false,
  canScrollPrev: false,
  canScrollNext: false,
};

function sameNavState(a: CalendarScrollNavState, b: CalendarScrollNavState): boolean {
  return a.canScrollTop === b.canScrollTop
    && a.canScrollPrev === b.canScrollPrev
    && a.canScrollNext === b.canScrollNext;
}

export function useCalendarScroll({
  isLoading,
  monthKeys,
  currentMonthKey,
  layoutVersion,
}: UseCalendarScrollOptions) {
  const calendarRef = useRef<HTMLDivElement | null>(null);
  const monthListRef = useRef<HTMLDivElement | null>(null);
  const monthAnchorRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const stickyToolsShellRef = useRef<HTMLDivElement | null>(null);
  const stickyToolsRef = useRef<HTMLDivElement | null>(null);
  const didScrollToCurrentMonthRef = useRef(false);
  const layoutMetricsRef = useRef<LayoutMetrics>(EMPTY_METRICS);
  const animationFrameRef = useRef<number | null>(null);
  const resizeFrameRef = useRef<number | null>(null);
  const [isCalendarToolsPinned, setIsCalendarToolsPinned] = useState(false);
  const [scrollNavState, setScrollNavState] = useState<CalendarScrollNavState>(EMPTY_NAV);

  const updateScrollState = useCallback(() => {
    const metrics = layoutMetricsRef.current;
    const scrollY = window.scrollY;
    const stickyOffset = metrics.headerHeight + metrics.toolsHeight;
    const focusedIndex = getFocusedMonthIndex(metrics.months, scrollY, stickyOffset);
    const nextNav = getCalendarScrollNavState({
      isDesktop: metrics.isDesktop,
      scrollY,
      viewportHeight: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      focusedIndex,
      monthCount: monthKeys.length,
    });

    setScrollNavState((current) => sameNavState(current, nextNav) ? current : nextNav);
    const nextPinned = metrics.isDesktop && scrollY + metrics.headerHeight > metrics.pinStart;
    setIsCalendarToolsPinned((current) => current === nextPinned ? current : nextPinned);
  }, [monthKeys.length]);

  const scheduleScrollUpdate = useCallback(() => {
    if (animationFrameRef.current !== null) return;
    animationFrameRef.current = window.requestAnimationFrame(() => {
      animationFrameRef.current = null;
      updateScrollState();
    });
  }, [updateScrollState]);

  const measureLayout = useCallback(() => {
    const calendar = calendarRef.current;
    const toolsShell = stickyToolsShellRef.current;
    const tools = stickyToolsRef.current;
    const app = calendar?.closest<HTMLElement>(".app");
    const appHeader = document.querySelector<HTMLElement>(".app-header");
    const isDesktop = window.matchMedia("(min-width: 1025px)").matches;

    if (!calendar || !toolsShell || !tools || !isDesktop) {
      tools?.style.removeProperty("--calendar-tools-left");
      tools?.style.removeProperty("--calendar-tools-width");
      calendar?.style.removeProperty("--calendar-rail-right");
      calendar?.style.removeProperty("--calendar-rail-lane");
      calendar?.removeAttribute("data-rail-reserved");
      app?.style.removeProperty("--calendar-header-height");
      toolsShell?.style.removeProperty("--calendar-tools-height");
      layoutMetricsRef.current = EMPTY_METRICS;
      updateScrollState();
      return;
    }

    const pageZoom = parseFloat(window.getComputedStyle(document.documentElement).zoom || "1") || 1;
    const calendarStyles = window.getComputedStyle(calendar);
    const calendarRect = calendar.getBoundingClientRect();
    const headerHeight = appHeader?.offsetHeight ?? 0;
    const toolsHeight = tools.offsetHeight;
    const shellRect = toolsShell.getBoundingClientRect();
    const currentRailLane = parseFloat(calendar.style.getPropertyValue("--calendar-rail-lane") || "0") || 0;
    const baseCalendarLeft = calendarRect.left / pageZoom - currentRailLane;
    const baseCalendarWidth = calendar.clientWidth + currentRailLane;
    const railButtonWidth = 68;
    const railGap = 8;
    const viewportInset = 8 / pageZoom;
    const railLane = Math.max(0, railButtonWidth + railGap + viewportInset - baseCalendarLeft);
    const calendarLeft = baseCalendarLeft + railLane;
    const paddingLeft = parseFloat(calendarStyles.paddingLeft || "0");
    const paddingRight = parseFloat(calendarStyles.paddingRight || "0");
    const contentLeft = calendarLeft + paddingLeft;
    const contentWidth = baseCalendarWidth - railLane - paddingLeft - paddingRight;
    const scrollY = window.scrollY;
    const monthBounds = monthKeys.flatMap(({ key }) => {
      const element = monthAnchorRefs.current.get(key);
      if (!element) return [];
      const rect = element.getBoundingClientRect();
      return [{ key, top: rect.top + scrollY, bottom: rect.bottom + scrollY }];
    });

    if (railLane > 0.5) {
      calendar.dataset.railReserved = "true";
      calendar.style.setProperty("--calendar-rail-lane", `${railLane}px`);
    } else {
      calendar.removeAttribute("data-rail-reserved");
      calendar.style.removeProperty("--calendar-rail-lane");
    }
    tools.style.setProperty("--calendar-tools-left", `${contentLeft}px`);
    tools.style.setProperty("--calendar-tools-width", `${contentWidth}px`);
    app?.style.setProperty("--calendar-header-height", `${headerHeight}px`);
    calendar.style.setProperty("--calendar-rail-right", `${calendarLeft - railGap}px`);
    toolsShell.style.setProperty("--calendar-tools-height", `${toolsHeight}px`);

    layoutMetricsRef.current = {
      isDesktop: true,
      headerHeight,
      toolsHeight,
      pinStart: shellRect.top + scrollY,
      months: monthBounds,
    };
    updateScrollState();
  }, [monthKeys, updateScrollState]);

  const scheduleMeasure = useCallback(() => {
    if (resizeFrameRef.current !== null) return;
    resizeFrameRef.current = window.requestAnimationFrame(() => {
      resizeFrameRef.current = null;
      measureLayout();
    });
  }, [measureLayout]);

  useEffect(() => {
    measureLayout();
    const app = calendarRef.current?.closest<HTMLElement>(".app");
    window.addEventListener("scroll", scheduleScrollUpdate, { passive: true });
    window.addEventListener("resize", scheduleMeasure);

    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleMeasure);
    for (const element of [
      calendarRef.current,
      stickyToolsShellRef.current,
      stickyToolsRef.current,
      monthListRef.current,
      document.querySelector<HTMLElement>(".app-header"),
    ]) {
      if (element) observer?.observe(element);
    }

    return () => {
      window.removeEventListener("scroll", scheduleScrollUpdate);
      window.removeEventListener("resize", scheduleMeasure);
      observer?.disconnect();
      if (animationFrameRef.current !== null) window.cancelAnimationFrame(animationFrameRef.current);
      if (resizeFrameRef.current !== null) window.cancelAnimationFrame(resizeFrameRef.current);
      app?.style.removeProperty("--calendar-header-height");
    };
  }, [isLoading, layoutVersion, measureLayout, scheduleMeasure, scheduleScrollUpdate]);

  useEffect(() => {
    didScrollToCurrentMonthRef.current = false;
  }, [currentMonthKey]);

  const getStickyOffset = useCallback(() => {
    const metrics = layoutMetricsRef.current;
    return metrics.isDesktop ? metrics.headerHeight + metrics.toolsHeight : 0;
  }, []);

  const scrollWindowToMonth = useCallback((key: string, behavior: ScrollBehavior = "smooth") => {
    const element = monthAnchorRefs.current.get(key);
    if (!element) return;
    const cached = layoutMetricsRef.current.months.find((month) => month.key === key);
    const absoluteTop = cached?.top ?? element.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: Math.max(0, absoluteTop - getStickyOffset() - 10), behavior });
  }, [getStickyOffset]);

  useEffect(() => {
    if (isLoading || didScrollToCurrentMonthRef.current) return;
    const monthList = monthListRef.current;
    const currentMonth = monthAnchorRefs.current.get(currentMonthKey);
    if (!monthList || !currentMonth) return;

    didScrollToCurrentMonthRef.current = true;
    if (window.matchMedia("(min-width: 1025px)").matches) {
      scrollWindowToMonth(currentMonthKey, "auto");
    } else {
      scrollCalendarMonthIntoContainer(monthList, currentMonth);
    }
    scheduleScrollUpdate();
  }, [currentMonthKey, isLoading, layoutVersion, scheduleScrollUpdate, scrollWindowToMonth]);

  const registerMonthAnchor = useCallback((key: string, element: HTMLDivElement | null) => {
    if (element) monthAnchorRefs.current.set(key, element);
    else monthAnchorRefs.current.delete(key);
  }, []);

  const handleScrollToTop = useCallback(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  const handleScrollToCurrentMonth = useCallback(() => {
    scrollWindowToMonth(currentMonthKey);
  }, [currentMonthKey, scrollWindowToMonth]);

  const handleScrollMonth = useCallback((delta: -1 | 1) => {
    const metrics = layoutMetricsRef.current;
    const focusedIndex = getFocusedMonthIndex(
      metrics.months,
      window.scrollY,
      metrics.headerHeight + metrics.toolsHeight,
    );
    if (focusedIndex < 0) return;
    const target = monthKeys[Math.max(0, Math.min(monthKeys.length - 1, focusedIndex + delta))];
    if (target) scrollWindowToMonth(target.key);
  }, [monthKeys, scrollWindowToMonth]);

  return {
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
  };
}
