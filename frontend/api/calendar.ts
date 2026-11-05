import type {
  AvailabilityResponse,
  BookingEligibility,
  BookingStatus,
  Cabin,
  CostPreview,
  MonthData,
} from "../types";
import { apiRequest } from "./client";

function withParams(path: string, params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export const calendarApi = {
  range: (startYear: number, startMonth: number, count: number, signal?: AbortSignal) =>
    apiRequest<{ months: MonthData[] }>(withParams("/api/calendar-range", {
      start_year: startYear,
      start_month: startMonth,
      count,
    }), { signal }),
  availability: (startDate: string, endDate: string, signal?: AbortSignal) =>
    apiRequest<AvailabilityResponse>(withParams("/api/availability", {
      start_date: startDate,
      end_date: endDate,
    }), { signal }),
  bookingStatus: (shareId?: string, signal?: AbortSignal) =>
    apiRequest<BookingStatus>(withParams("/api/booking-status", { share: shareId }), { signal }),
  eligibility: (startDate: string, endDate: string, shareId: string, signal?: AbortSignal) =>
    apiRequest<BookingEligibility>(withParams("/api/booking-eligibility", {
      start_date: startDate,
      end_date: endDate,
      share: shareId,
    }), { signal }),
  cost: (input: {
    startDate: string;
    endDate: string;
    cabins: string[];
    isDayUse: boolean;
    guestNights: number[];
  }, signal?: AbortSignal) => apiRequest<CostPreview>(withParams("/api/booking-cost", {
    start_date: input.startDate,
    end_date: input.endDate,
    cabins: input.cabins.join(","),
    is_day_use: input.isDayUse,
    guest_count: input.guestNights.length,
    guest_nights: input.guestNights.join(","),
  }), { signal }),
  cabins: (signal?: AbortSignal) => apiRequest<Cabin[]>("/api/cabins", { signal }),
};
