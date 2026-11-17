import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setToken, setUnauthorizedHandler } from "./api.js";

// The login session: who is logged in, and their token.
// Kept in sessionStorage, so it survives a page refresh but ends when the browser tab is closed.
// (In a production system a secure, httpOnly cookie would be preferred.)

const KEY = "payreliant.session";
const AuthContext = createContext(null);

function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY)) || null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSession); // { token, user } or null
  setToken(session?.token ?? null);

  const logout = useCallback(() => {
    try { sessionStorage.removeItem(KEY); } catch { /* storage unavailable: nothing to clear */ }
    setToken(null);
    setSession(null);
  }, []);

  useEffect(() => { setUnauthorizedHandler(logout); }, [logout]);

  const login = useCallback(async (username, password) => {
    const data = await api.login(username, password);
    const next = { token: data.access_token, user: data.user };
    try { sessionStorage.setItem(KEY, JSON.stringify(next)); } catch { /* still works for this page */ }
    setToken(next.token);
    setSession(next);
    return next.user;
  }, []);

  const value = useMemo(() => ({
    user: session?.user ?? null,
    isAdmin: session?.user?.role === "ADMIN",
    login,
    logout,
  }), [session, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
