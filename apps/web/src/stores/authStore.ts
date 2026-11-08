/**
 * Auth store — access token lives in memory only (Rule §5.11).
 * Refresh token is managed via httpOnly cookie on the real server;
 * in dev mode we store it in sessionStorage as a fallback (never localStorage).
 */

import { create } from 'zustand';

export interface AuthState {
  /** JWT access token; null = unauthenticated */
  accessToken: string | null;
  /** Decoded role from the JWT claims */
  role: string | null;
  /** manager_id from the JWT claims (if role=manager or super_admin) */
  managerId: string | null;
  /** client_id from the JWT claims (if role=client) */
  clientId: string | null;
  /** user_id from the JWT sub claim */
  userId: string | null;
  /** Active impersonated manager for super_admin */
  impersonatedManagerId: string | null;
  impersonatedManagerName: string | null;
  /** Epoch ms when the token expires */
  expiresAt: number | null;
  /** Set token after successful login/refresh */
  setToken: (token: string, expiresIn: number) => void;
  /** Set or clear impersonation */
  setImpersonation: (managerId: string | null, name: string | null) => void;
  /** Clear token on logout */
  clearToken: () => void;
}

function parseJwtPayload(token: string): Record<string, unknown> {
  try {
    const [, payload] = token.split('.');
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    return {};
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  role: null,
  managerId: null,
  clientId: null,
  userId: null,
  impersonatedManagerId: null,
  impersonatedManagerName: null,
  expiresAt: null,

  setToken(token, expiresIn) {
    const payload = parseJwtPayload(token);
    set({
      accessToken: token,
      role: (payload['role'] as string) ?? null,
      managerId: (payload['manager_id'] as string) ?? null,
      clientId: (payload['client_id'] as string) ?? null,
      userId: (payload['sub'] as string) ?? null,
      expiresAt: Date.now() + expiresIn * 1000,
    });
  },

  setImpersonation(managerId, name) {
    set({ impersonatedManagerId: managerId, impersonatedManagerName: name });
  },

  clearToken() {
    set({
      accessToken: null,
      role: null,
      managerId: null,
      clientId: null,
      userId: null,
      impersonatedManagerId: null,
      impersonatedManagerName: null,
      expiresAt: null,
    });
  },
}));

/** Selector: true when the user is authenticated with a non-expired token */
export function useIsAuthenticated(): boolean {
  const { accessToken, expiresAt } = useAuthStore();
  return !!accessToken && !!expiresAt && Date.now() < expiresAt;
}
