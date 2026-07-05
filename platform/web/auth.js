// Lightweight auth: talks to /api/v1/auth, stores tokens, exposes a React hook.
// Deliberately standalone (localStorage + context) rather than wired into the
// DashCode Redux store, so it stays simple and portable across scenarios.
"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, tokens } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | authed | anon

  const loadMe = useCallback(async () => {
    if (!tokens.access) {
      setStatus("anon");
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      setStatus("authed");
    } catch {
      tokens.clear();
      setUser(null);
      setStatus("anon");
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = useCallback(
    async (email, password) => {
      const { data } = await api.post("/auth/login", { email, password });
      // When 2FA is on, the backend withholds tokens and returns a challenge —
      // surface it so the caller can prompt for the authenticator code.
      if (data.mfa_required) return { mfaRequired: true, mfaToken: data.mfa_token };
      tokens.set(data.access_token, data.refresh_token);
      await loadMe();
      return { mfaRequired: false };
    },
    [loadMe]
  );

  // Second step of a 2FA login: exchange the challenge token + a TOTP/recovery
  // code for real tokens.
  const loginMfa = useCallback(
    async (mfaToken, code) => {
      const { data } = await api.post("/auth/login/mfa", { mfa_token: mfaToken, code });
      tokens.set(data.access_token, data.refresh_token);
      await loadMe();
    },
    [loadMe]
  );

  const logout = useCallback(async () => {
    try {
      if (tokens.refresh) await api.post("/auth/logout", { refresh_token: tokens.refresh });
    } catch {
      /* best-effort */
    }
    tokens.clear();
    setUser(null);
    setStatus("anon");
  }, []);

  // permission check against the user's dynamic role ("*" = admin)
  const can = useCallback(
    (perm) => {
      const perms = user?.role?.permissions || [];
      return perms.includes("*") || perms.includes(perm);
    },
    [user]
  );

  return (
    <AuthContext.Provider value={{ user, status, login, loginMfa, logout, can, reload: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
