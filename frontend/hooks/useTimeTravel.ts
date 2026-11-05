import { useState, useEffect, useCallback } from "react";
import { fetchJsonCached, invalidateGetCache } from "../lib/fetchCache";

interface TimeTravelState {
  isActive: boolean;
  simulatedDate: string | null;
  effectiveToday: string;
  refresh: () => void;
}

function realToday(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function useTimeTravel(enabled = true): TimeTravelState {
  const [isActive, setIsActive] = useState(false);
  const [simulatedDate, setSimulatedDate] = useState<string | null>(null);

  const fetchStatus = useCallback(async (force = false) => {
    if (!enabled) return;
    if (force) invalidateGetCache("/api/time-travel/status");

    try {
      const data = await fetchJsonCached<{ active: boolean; simulated_date: string | null }>(
        "/api/time-travel/status",
        { credentials: "include" },
        { ttlMs: 30000, bypassCache: force, dedupe: !force }
      );
      setIsActive(data.active);
      setSimulatedDate(data.simulated_date);
    } catch {
      // Silently fail - not critical
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setIsActive(false);
      setSimulatedDate(null);
      return;
    }
    fetchStatus();
  }, [enabled, fetchStatus]);

  const effectiveToday = isActive && simulatedDate ? simulatedDate : realToday();

  const refresh = useCallback(() => {
    void fetchStatus(true);
  }, [fetchStatus]);

  return { isActive, simulatedDate, effectiveToday, refresh };
}
