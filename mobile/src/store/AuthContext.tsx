import React, {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Platform } from "react-native";
import * as authApi from "../api/auth";
import {
  clearTokens,
  getAccessToken,
  getDeviceId,
  getRefreshToken,
  getTokenExpiresAt,
  storeDeviceId,
  storeTokens,
} from "./secureStorage";
import { TOKEN_REFRESH_MARGIN_SECONDS } from "../config";

// ---- Types ----

export interface AuthState {
  /** Whether the initial token probe has completed. */
  isLoading: boolean;
  /** Whether the user has valid tokens stored. */
  isAuthenticated: boolean;
}

export interface AuthActions {
  /** Exchange a license key for tokens. */
  activate: (licenseKey: string) => Promise<void>;
  /** Explicitly log out and revoke the refresh token. */
  logout: () => Promise<void>;
}

export type AuthContextValue = AuthState & AuthActions;

// ---- Context ----

export const AuthContext = createContext<AuthContextValue>({
  isLoading: true,
  isAuthenticated: false,
  activate: async () => {},
  logout: async () => {},
});

// ---- Helpers ----

function generateDeviceId(): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `mobile-${Platform.OS}-${random}-${Date.now()}`;
}

// ---- Provider ----

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Schedule a silent token refresh before the access token expires.
  const scheduleRefresh = useCallback(async () => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    const expiresAt = await getTokenExpiresAt();
    if (!expiresAt) return;

    const msUntilRefresh =
      expiresAt - Date.now() - TOKEN_REFRESH_MARGIN_SECONDS * 1000;

    if (msUntilRefresh <= 0) {
      // Token already near-expired -- refresh now.
      await doRefresh();
      return;
    }

    refreshTimerRef.current = setTimeout(() => {
      doRefresh();
    }, msUntilRefresh);
  }, []);

  const doRefresh = useCallback(async () => {
    try {
      const rt = await getRefreshToken();
      if (!rt) {
        setIsAuthenticated(false);
        return;
      }
      const tokens = await authApi.refresh(rt);
      await storeTokens(
        tokens.access_token,
        tokens.refresh_token,
        tokens.expires_in,
        tokens.refresh_expires_in,
      );
      setIsAuthenticated(true);
      await scheduleRefresh();
    } catch {
      // Refresh failed -- user will need to re-activate.
      await clearTokens();
      setIsAuthenticated(false);
    }
  }, [scheduleRefresh]);

  // On mount: check if we already have a valid token.
  useEffect(() => {
    (async () => {
      const token = await getAccessToken();
      if (token) {
        setIsAuthenticated(true);
        await scheduleRefresh();
      }
      setIsLoading(false);
    })();

    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, [scheduleRefresh]);

  // ---- Actions ----

  const activate = useCallback(
    async (licenseKey: string) => {
      let deviceId = await getDeviceId();
      if (!deviceId) {
        deviceId = generateDeviceId();
        await storeDeviceId(deviceId);
      }

      const tokens = await authApi.activate(licenseKey, deviceId);
      await storeTokens(
        tokens.access_token,
        tokens.refresh_token,
        tokens.expires_in,
        tokens.refresh_expires_in,
      );
      setIsAuthenticated(true);
      await scheduleRefresh();
    },
    [scheduleRefresh],
  );

  const logout = useCallback(async () => {
    try {
      const rt = await getRefreshToken();
      if (rt) await authApi.revoke(rt);
    } catch {
      // Best-effort revocation; clear local state regardless.
    }
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    await clearTokens();
    setIsAuthenticated(false);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ isLoading, isAuthenticated, activate, logout }),
    [isLoading, isAuthenticated, activate, logout],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}
