import type { BookingSeason, Reservation, Shareholder } from "../types";
import { adminApi } from "./admin";
import { reservationsApi } from "./reservations";

export interface AdminDashboardData {
  reservations: Reservation[];
  season: BookingSeason | null;
  seasons: BookingSeason[];
  shareholders: Shareholder[];
}
function requireArray<T>(value: T[], label: string): T[] {
  if (!Array.isArray(value)) {
    throw new Error(`The server returned invalid ${label} data.`);
  }
  return value;
}

export async function loadAdminDashboardData(signal?: AbortSignal): Promise<AdminDashboardData> {
  const [reservations, season, seasons, shareholders] = await Promise.all([
    reservationsApi.list({ includeCancelled: true, signal }),
    adminApi.currentSeason(signal),
    adminApi.seasons(signal),
    adminApi.shareholders(signal),
  ]);

  return {
    reservations: requireArray(reservations, "reservation"),
    season,
    seasons: requireArray(seasons, "season"),
    shareholders: requireArray(shareholders, "shareholder"),
  };
}
