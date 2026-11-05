import { CalendarDay } from "./CalendarDay";
import type {
  CalendarDay as CalendarDayType,
  Cabin,
  ReservationSegmentMeta,
} from "../types";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

interface CalendarMonthProps {
  year: number;
  month: number; // 1-indexed
  days: CalendarDayType[];
  todayStr: string;
  startDate: string | null;
  endDate: string | null;
  isInRange: (date: string) => boolean;
  isSelectable: (date: string) => boolean;
  isFullyBooked: (day: CalendarDayType) => boolean;
  isBookedDay: (day: CalendarDayType) => boolean;
  isCheckoutSelectableDay: (day: CalendarDayType) => boolean;
  onDayClick: (day: CalendarDayType) => void;
  getReservationSegment: (date: string, reservationId: number, cabinId: string) => ReservationSegmentMeta;
  cabins: Cabin[];
  showWeekdays?: boolean;
}

export function CalendarMonth({
  year,
  month,
  days,
  todayStr,
  startDate,
  endDate,
  isInRange,
  isSelectable,
  isFullyBooked,
  isBookedDay,
  isCheckoutSelectableDay,
  onDayClick,
  getReservationSegment,
  cabins,
  showWeekdays = true,
}: CalendarMonthProps) {
  const firstDayOfMonth = new Date(year, month - 1, 1).getDay();

  return (
    <div className="calendar-month">
      <h3 className="calendar-month-label">
        {MONTHS[month - 1]} {year}
      </h3>
      {showWeekdays && (
        <div className="calendar-weekdays">
          {WEEKDAYS.map((day) => (
            <div key={day} className="weekday">
              {day}
            </div>
          ))}
        </div>
      )}
      <div className="calendar-grid">
        {Array.from({ length: firstDayOfMonth }).map((_, i) => (
          <div key={`empty-${year}-${month}-${i}`} className="calendar-day empty" />
        ))}
        {days.map((day) => (
          <CalendarDay
            key={day.date}
            day={day}
            isToday={day.date === todayStr}
            isSelected={day.date === startDate || day.date === endDate}
            isInRange={isInRange(day.date)}
            isSelectable={isSelectable(day.date)}
            isFullyBooked={isFullyBooked(day)}
            isBooked={isBookedDay(day)}
            isCheckoutSelectable={isCheckoutSelectableDay(day)}
            onClick={() => onDayClick(day)}
            getReservationSegment={getReservationSegment}
            cabins={cabins}
          />
        ))}
      </div>
    </div>
  );
}
