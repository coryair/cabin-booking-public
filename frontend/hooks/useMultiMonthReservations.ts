import { useState, useEffect, useCallback, useMemo } from "react";
import type { MonthData } from "../types";
import { calendarApi } from "../api/calendar";

export function shouldFinishCalendarLoading(silent: boolean, signal?: Pick<AbortSignal, "aborted">): boolean {
  return !silent && !signal?.aborted;
}

export function useMultiMonthReservations(startYear: number, startMonth: number, count: number) {
  const [months, setMonths] = useState<Map<string, MonthData>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getMonthKeys = useCallback(() => {
    const keys: { year: number; month: number; key: string }[] = [];
    let y = startYear;
    let m = startMonth;
    for (let i = 0; i < count; i++) {
      keys.push({ year: y, month: m, key: `${y}-${String(m).padStart(2, "0")}` });
      m++;
      if (m > 12) { m = 1; y++; }
    }
    return keys;
  }, [startYear, startMonth, count]);

  const fetchAll = useCallback(async (silent = false, signal?: AbortSignal) => {
    if (!silent) setIsLoading(true);
    setError(null);

    try {
      const keys = getMonthKeys();
      if (keys.length === 0) {
        setMonths(new Map());
        return;
      }

      const first = keys[0]!;
      const data = await calendarApi.range(first.year, first.month, keys.length, signal);
      const results = (data.months || []).map((monthData) => {
        const key = `${monthData.year}-${String(monthData.month).padStart(2, "0")}`;
        return [key, monthData] as const;
      });

      setMonths(new Map(results));
    } catch (err) {
      if (signal?.aborted) return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (shouldFinishCalendarLoading(silent, signal)) setIsLoading(false);
    }
  }, [getMonthKeys]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchAll(false, controller.signal);
    return () => controller.abort();
  }, [fetchAll]);

  const checkAvailability = useCallback(async (
    startDate: string,
    endDate: string,
    signal?: AbortSignal,
  ): Promise<Record<string, boolean>> => {
    const data = await calendarApi.availability(startDate, endDate, signal);
    return data.cabins;
  }, []);

  const monthKeys = useMemo(getMonthKeys, [getMonthKeys]);

  return {
    months,
    monthKeys,
    isLoading,
    error,
    refreshAll: fetchAll,
    checkAvailability,
  };
}
