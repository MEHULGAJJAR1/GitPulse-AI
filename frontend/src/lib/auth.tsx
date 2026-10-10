import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, api, getApiKey, onAuthChange, setApiKey } from "./api";
import type { Role } from "./types";

interface Me {
  role: Role;
  can_see_private_repos: boolean;
  private_repos_enabled: boolean;
  llm: { enabled: boolean; provider: string; model: string | null };
}

interface AuthState {
  me: Me | null;
  loading: boolean;
  /** Set when the session could not be verified for a reason other than an invalid key (e.g. API unreachable). */
  sessionError: unknown;
  retrySession: () => void;
  login: (key: string) => Promise<void>;
  logout: () => void;
  can: (role: Role) => boolean;
}

const RANK: Record<Role, number> = { viewer: 1, analyst: 2, admin: 3 };
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState<boolean>(!!getApiKey());
  const [sessionError, setSessionError] = useState<unknown>(null);

  const refresh = useCallback(async () => {
    if (!getApiKey()) {
      setMe(null);
      setSessionError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setMe(await api.get<Me>("/me"));
      setSessionError(null);
    } catch (err) {
      setMe(null);
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        // The stored key is no longer valid: end the session.
        setApiKey(null);
        setSessionError(null);
      } else {
        // Transient failure (server down, timeout, 5xx): keep the key and let the user retry.
        setSessionError(err);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    return onAuthChange(() => {
      if (!getApiKey()) {
        setMe(null);
        setSessionError(null);
      }
    });
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      sessionError,
      retrySession: () => {
        void refresh();
      },
      login: async (key: string) => {
        setApiKey(key.trim());
        try {
          const profile = await api.get<Me>("/me");
          setMe(profile);
        } catch (err) {
          setApiKey(null);
          throw err;
        }
      },
      logout: () => {
        setApiKey(null);
        setMe(null);
      },
      can: (role: Role) => (me ? RANK[me.role] >= RANK[role] : false),
    }),
    [me, loading, sessionError, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
