import { useState, useEffect, useCallback, useRef } from "react";
import type { Shareholder } from "../types";
import { fetchJsonCached, invalidateGetCache } from "../lib/fetchCache";
import { authApi, type AuthCheckResult } from "../api/auth";

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  shareholder: Shareholder | null;
  isViewer: boolean;
  isAnalytics: boolean;
  isAdmin: boolean;
  isSuperadmin: boolean;
}

export function useAuth() {
  const requestGenerationRef = useRef(0);
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    error: null,
    shareholder: null,
    isViewer: false,
    isAnalytics: false,
    isAdmin: false,
    isSuperadmin: false,
  });

  const checkAuth = useCallback(async (force = false) => {
    const requestGeneration = ++requestGenerationRef.current;
    if (force) invalidateGetCache("/api/auth/check");

    try {
      const data = await fetchJsonCached<AuthCheckResult>(
        "/api/auth/check",
        { credentials: "include" },
        { ttlMs: 5000, bypassCache: force, dedupe: !force }
      );
      if (requestGeneration !== requestGenerationRef.current) return;
      const sh = data.shareholder || null;
      setState({
        isAuthenticated: data.authenticated,
        isLoading: false,
        error: null,
        shareholder: sh,
        isViewer: sh?.is_viewer || false,
        isAnalytics: sh?.is_analytics || false,
        isAdmin: sh?.is_admin || false,
        isSuperadmin: sh?.is_superadmin || false,
      });
    } catch {
      if (requestGeneration !== requestGenerationRef.current) return;
      setState({
        isAuthenticated: false,
        isLoading: false,
        error: "Failed to check authentication",
        shareholder: null,
        isViewer: false,
        isAnalytics: false,
        isAdmin: false,
        isSuperadmin: false,
      });
    }
  }, []);

  useEffect(() => {
    void checkAuth();
    return () => {
      requestGenerationRef.current += 1;
    };
  }, [checkAuth]);

  const login = async (email: string, password: string): Promise<boolean> => {
    const requestGeneration = ++requestGenerationRef.current;
    setState((s) => ({ ...s, error: null, isLoading: true }));

    try {
      const data = await authApi.login(email, password);
      invalidateGetCache("/api/auth/check");
      const sh = data.shareholder;
      if (requestGeneration !== requestGenerationRef.current) return false;
      setState({
        isAuthenticated: true,
        isLoading: false,
        error: null,
        shareholder: sh,
        isViewer: sh.is_viewer,
        isAnalytics: sh.is_analytics,
        isAdmin: sh.is_admin,
        isSuperadmin: sh.is_superadmin,
      });
      return true;
    } catch (error) {
      if (requestGeneration !== requestGenerationRef.current) return false;
      setState({
        isAuthenticated: false,
        isLoading: false,
        error: error instanceof Error ? error.message : "Login failed",
        shareholder: null,
        isViewer: false,
        isAnalytics: false,
        isAdmin: false,
        isSuperadmin: false,
      });
      return false;
    }
  };

  const sendMagicLink = async (email: string): Promise<boolean> => {
    try {
      await authApi.sendMagicLink(email);
      return true;
    } catch {
      return false;
    }
  };

  const updateCancellationAvailabilityPreference = async (enabled: boolean): Promise<void> => {
    const shareholder = await authApi.updateNotificationPreferences(enabled);
    invalidateGetCache("/api/auth/check");
    setState((current) => ({
      ...current,
      shareholder,
      isViewer: shareholder.is_viewer,
      isAnalytics: shareholder.is_analytics,
      isAdmin: shareholder.is_admin,
      isSuperadmin: shareholder.is_superadmin,
    }));
  };

  const logout = async (): Promise<void> => {
    requestGenerationRef.current += 1;
    try {
      await authApi.logout();
    } finally {
      requestGenerationRef.current += 1;
      invalidateGetCache("/api/auth/check");
      setState({
        isAuthenticated: false,
        isLoading: false,
        error: null,
        shareholder: null,
        isViewer: false,
        isAnalytics: false,
        isAdmin: false,
        isSuperadmin: false,
      });
    }
  };

  return {
    ...state,
    login,
    logout,
    checkAuth,
    sendMagicLink,
    updateCancellationAvailabilityPreference,
  };
}
