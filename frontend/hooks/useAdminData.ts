import { useState, useEffect, useMemo } from "react";
import type { Reservation, BookingSeason, Shareholder } from "../types";
import { isActive } from "../utils";
import { loadAdminDashboardData } from "../api/adminData";

export function useAdminData() {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [season, setSeason] = useState<BookingSeason | null>(null);
  const [seasons, setSeasons] = useState<BookingSeason[]>([]);
  const [shareholders, setShareholders] = useState<Shareholder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await loadAdminDashboardData(controller.signal);
        if (controller.signal.aborted) return;
        setReservations(data.reservations);
        setSeason(data.season);
        setSeasons(data.seasons);
        setShareholders(data.shareholders);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Failed to load admin data");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, []);

  const active = useMemo(() => reservations.filter(isActive), [reservations]);

  return { reservations, season, seasons, shareholders, active, loading, error };
}
