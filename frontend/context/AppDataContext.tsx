import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { useBookingStatus } from "../hooks/useBookingStatus";
import { useTimeTravel } from "../hooks/useTimeTravel";
import { fetchJsonCached, invalidateGetCache } from "../lib/fetchCache";
import type { AllowedShare, BookingStatus, Cabin, Shareholder } from "../types";

type AppDataContextValue = {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  shareholder: Shareholder | null;
  allowedShares: AllowedShare[];
  activeShareId: string | null;
  activeShare: AllowedShare | null;
  setActiveShareId: (shareId: string) => void;
  isViewer: boolean;
  isAnalytics: boolean;
  isAdmin: boolean;
  isSuperadmin: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  checkAuth: (force?: boolean) => Promise<void>;
  sendMagicLink: (email: string) => Promise<boolean>;
  updateCancellationAvailabilityPreference: (enabled: boolean) => Promise<void>;
  timeTravelActive: boolean;
  simulatedDate: string | null;
  effectiveToday: string;
  refreshTimeTravel: () => void;
  bookingStatus: BookingStatus | null;
  bookingStatusLoading: boolean;
  refreshBookingStatus: () => void;
  cabins: Cabin[];
  cabinsLoading: boolean;
  cabinsError: string | null;
  refreshCabins: () => Promise<void>;
};

const AppDataContext = createContext<AppDataContextValue | null>(null);

interface AppDataProviderProps {
  children: ReactNode;
  currentPath?: string;
}

function getAllowedShares(shareholder: Shareholder | null): AllowedShare[] {
  if (!shareholder) return [];
  if (shareholder.allowed_shares?.length) return shareholder.allowed_shares;
  return [{
    share_id: shareholder.share,
    share_name: shareholder.share_name || shareholder.share,
    priority: shareholder.priority,
  }];
}

export function AppDataProvider({ children, currentPath = window.location.pathname }: AppDataProviderProps) {
  const auth = useAuth();
  const isAdminRoute = currentPath.startsWith("/admin");
  const isCalendarRoute = currentPath === "/";
  const { isActive, simulatedDate, effectiveToday, refresh } = useTimeTravel(auth.isAuthenticated);
  const allowedShares = useMemo(() => getAllowedShares(auth.shareholder), [auth.shareholder]);
  const [activeShareIdState, setActiveShareIdState] = useState<string | null>(null);
  const resolvedActiveShareId = activeShareIdState ?? auth.shareholder?.share ?? allowedShares[0]?.share_id ?? null;
  const bookingEnabled = auth.isAuthenticated && !isAdminRoute && Boolean(resolvedActiveShareId);
  const booking = useBookingStatus(
    bookingEnabled,
    resolvedActiveShareId ?? undefined
  );
  const refreshBookingStatusOnRouteEntry = booking.refresh;
  const wasCalendarRouteRef = useRef(isCalendarRoute);
  const wasBookingEnabledRef = useRef(bookingEnabled);

  useEffect(() => {
    const enteringCalendar = isCalendarRoute && !wasCalendarRouteRef.current;
    const bookingStayedEnabled = bookingEnabled && wasBookingEnabledRef.current;
    wasCalendarRouteRef.current = isCalendarRoute;
    wasBookingEnabledRef.current = bookingEnabled;

    if (enteringCalendar && bookingStayedEnabled) {
      refreshBookingStatusOnRouteEntry();
    }
  }, [bookingEnabled, isCalendarRoute, refreshBookingStatusOnRouteEntry]);

  const [cabins, setCabins] = useState<Cabin[]>([]);
  const [cabinsLoading, setCabinsLoading] = useState(false);
  const [cabinsError, setCabinsError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth.isAuthenticated || !auth.shareholder) {
      setActiveShareIdState(null);
      return;
    }

    const validShareIds = new Set(allowedShares.map((share) => share.share_id));
    const storageKey = `activeShare:${auth.shareholder.id}`;
    const storedShareId = window.localStorage.getItem(storageKey);
    const primaryShareId = auth.shareholder.share;

    setActiveShareIdState((current) => {
      if (current && validShareIds.has(current)) return current;
      if (storedShareId && validShareIds.has(storedShareId)) return storedShareId;
      if (primaryShareId && validShareIds.has(primaryShareId)) return primaryShareId;
      return allowedShares[0]?.share_id ?? null;
    });
  }, [auth.isAuthenticated, auth.shareholder, allowedShares]);

  useEffect(() => {
    if (!auth.shareholder) return;

    const storageKey = `activeShare:${auth.shareholder.id}`;
    if (resolvedActiveShareId && allowedShares.some((share) => share.share_id === resolvedActiveShareId)) {
      window.localStorage.setItem(storageKey, resolvedActiveShareId);
      return;
    }

    window.localStorage.removeItem(storageKey);
  }, [auth.shareholder, resolvedActiveShareId, allowedShares]);

  const activeShare = useMemo(
    () => allowedShares.find((share) => share.share_id === resolvedActiveShareId) ?? null,
    [allowedShares, resolvedActiveShareId]
  );

  const setActiveShareId = useCallback((shareId: string) => {
    if (!allowedShares.some((share) => share.share_id === shareId)) return;
    if (auth.shareholder) {
      window.localStorage.setItem(`activeShare:${auth.shareholder.id}`, shareId);
    }
    setActiveShareIdState(shareId);
  }, [allowedShares, auth.shareholder]);

  const fetchCabins = useCallback(async (force = false) => {
    if (!auth.isAuthenticated) return;
    if (force) invalidateGetCache("/api/cabins");

    setCabinsLoading(true);
    setCabinsError(null);

    try {
      const data = await fetchJsonCached<Cabin[]>(
        "/api/cabins",
        { credentials: "include" },
        { ttlMs: 60000, bypassCache: force }
      );
      setCabins(Array.isArray(data) ? data : []);
    } catch {
      setCabinsError("Failed to load cabin data");
    } finally {
      setCabinsLoading(false);
    }
  }, [auth.isAuthenticated]);

  useEffect(() => {
    if (!auth.isAuthenticated) {
      setCabins([]);
      setCabinsError(null);
      setCabinsLoading(false);
      return;
    }
    void fetchCabins();
  }, [auth.isAuthenticated, fetchCabins]);

  const value = useMemo<AppDataContextValue>(() => ({
    isAuthenticated: auth.isAuthenticated,
    isLoading: auth.isLoading,
    error: auth.error,
    shareholder: auth.shareholder,
    allowedShares,
    activeShareId: resolvedActiveShareId,
    activeShare,
    setActiveShareId,
    isViewer: auth.isViewer,
    isAnalytics: auth.isAnalytics,
    isAdmin: auth.isAdmin,
    isSuperadmin: auth.isSuperadmin,
    login: auth.login,
    logout: auth.logout,
    checkAuth: auth.checkAuth,
    sendMagicLink: auth.sendMagicLink,
    updateCancellationAvailabilityPreference: auth.updateCancellationAvailabilityPreference,
    timeTravelActive: isActive,
    simulatedDate,
    effectiveToday,
    refreshTimeTravel: refresh,
    bookingStatus: booking.status,
    bookingStatusLoading: booking.isLoading,
    refreshBookingStatus: booking.refresh,
    cabins,
    cabinsLoading,
    cabinsError,
    refreshCabins: () => fetchCabins(true),
  }), [
    auth.isAuthenticated,
    auth.isLoading,
    auth.error,
    auth.shareholder,
    allowedShares,
    resolvedActiveShareId,
    activeShare,
    setActiveShareId,
    auth.isViewer,
    auth.isAnalytics,
    auth.isAdmin,
    auth.isSuperadmin,
    auth.login,
    auth.logout,
    auth.checkAuth,
    auth.sendMagicLink,
    auth.updateCancellationAvailabilityPreference,
    isActive,
    simulatedDate,
    effectiveToday,
    refresh,
    booking.status,
    booking.isLoading,
    booking.refresh,
    cabins,
    cabinsLoading,
    cabinsError,
    fetchCabins,
  ]);

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppDataContextValue {
  const ctx = useContext(AppDataContext);
  if (!ctx) {
    throw new Error("useAppData must be used within AppDataProvider");
  }
  return ctx;
}
