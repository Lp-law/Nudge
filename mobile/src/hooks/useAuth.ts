import { useContext } from "react";
import { AuthContext, AuthContextValue } from "../store/AuthContext";

/**
 * Convenience hook for consuming auth state and actions.
 *
 * Usage:
 *   const { isAuthenticated, activate, logout } = useAuth();
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an <AuthProvider>");
  }
  return ctx;
}
