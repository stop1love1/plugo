import { create } from "zustand";

type User = {
  username: string;
  role: string;
  // Vestigial: the JWT now lives in an httpOnly cookie set by the backend and is
  // never stored in JS. Kept optional so callers may still pass it in-memory.
  token?: string;
};

type Store = {
  user: User | null;
  setUser: (user: User | null) => void;
  logout: () => void;
};

// Auth rides on an httpOnly `plugo_token` cookie (not readable by JS), so the
// token is never persisted client-side — only the profile, so the dashboard can
// render before the first re-auth. If the cookie is missing/expired the first
// API call 401s and the interceptor bounces to /login.
let initialUser: User | null = null;
try {
  const savedUser = localStorage.getItem("plugo_user");
  initialUser = savedUser ? (JSON.parse(savedUser) as User) : null;
} catch {
  localStorage.removeItem("plugo_user");
}

export const useStore = create<Store>((set) => ({
  user: initialUser,
  setUser: (user) => {
    if (user) {
      // Persist profile only — never the token.
      localStorage.setItem(
        "plugo_user",
        JSON.stringify({ username: user.username, role: user.role }),
      );
    } else {
      localStorage.removeItem("plugo_user");
    }
    set({ user });
  },
  logout: () => {
    localStorage.removeItem("plugo_user");
    set({ user: null });
  },
}));
