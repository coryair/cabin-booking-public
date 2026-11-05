export interface CalendarWindow {
  startYear: number;
  startMonth: number;
  count: number;
  currentMonthKey: string;
}

export function getCalendarWindow(currentYear: number, currentMonth: number, forwardMonthCount: number): CalendarWindow {
  const startMonth = 1;
  const monthsBeforeCurrent = currentMonth - startMonth;

  return {
    startYear: currentYear,
    startMonth,
    count: monthsBeforeCurrent + forwardMonthCount,
    currentMonthKey: `${currentYear}-${String(currentMonth).padStart(2, "0")}`,
  };
}
