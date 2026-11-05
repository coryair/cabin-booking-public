import { useState, useEffect, useCallback, useRef } from "react";
import type { BookingStatus } from "../types";
import { fetchJsonCached, invalidateGetCache } from "../lib/fetchCache";

interface ShareBookingStatus {
  shareId?: string;
  value: BookingStatus;
}

export function useBookingStatus(enabled = true, shareId?: string) {
  const [statusState, setStatusState] = useState<ShareBookingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestGenerationRef = useRef(0);
  const wasEnabledRef = useRef(enabled);
  const previousShareIdRef = useRef(shareId);

  const fetchStatus = useCallback(async (force = false) => {
    if (!enabled) return;
    const requestGeneration = ++requestGenerationRef.current;
    const params = new URLSearchParams();
    if (shareId) params.set("share", shareId);
    const url = params.size > 0 ? `/api/booking-status?${params.toString()}` : "/api/booking-status";

    if (force) invalidateGetCache("/api/booking-status");

    setIsLoading(true);
    setError(null);

    try {
      const data = await fetchJsonCached<BookingStatus>(
        url,
        { credentials: "include" },
        { ttlMs: 15000, bypassCache: force, dedupe: !force }
      );
      if (requestGeneration !== requestGenerationRef.current) return;
      setStatusState({ shareId, value: data });
    } catch (err) {
      if (requestGeneration !== requestGenerationRef.current) return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (requestGeneration === requestGenerationRef.current) {
        setIsLoading(false);
      }
    }
  }, [enabled, shareId]);

  useEffect(() => {
    const wasEnabled = wasEnabledRef.current;
    const shareChanged = previousShareIdRef.current !== shareId;
    wasEnabledRef.current = enabled;
    previousShareIdRef.current = shareId;

    if (!enabled) {
      requestGenerationRef.current += 1;
      setStatusState(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    void fetchStatus(!wasEnabled || shareChanged);

    return () => {
      requestGenerationRef.current += 1;
    };
  }, [enabled, fetchStatus, shareId]);

  const refresh = useCallback(() => {
    void fetchStatus(true);
  }, [fetchStatus]);

  return {
    status: statusState && statusState.shareId === shareId ? statusState.value : null,
    isLoading,
    error,
    refresh,
  };
}
