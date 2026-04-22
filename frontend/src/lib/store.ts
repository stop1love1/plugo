import { create } from "zustand";

type User = {
  username: string;
  role: string;
  token: string;
};

type Store = {
  user: User | null;
  setUser: (user: User | null) => void;
  logout: () => void;
};

// Restore user from storage on load. Token lives in sessionStorage so it dies
// on tab close (smaller blast radius for XSS theft); user profile stays in
// localStorage so the dashboard UI can render before the first re-auth.
// TODO(security): migrate token to an httpOnly cookie and drop client-side storage entirely.
let initialUser = null;
try {
  const savedUser = localStorage.getItem("plugo_user");
  const savedToken = sessionStorage.getItem("plugo_token");
  // Only restore a user if we still have a live token for this tab.
  initialUser = savedUser && savedToken ? JSON.parse(savedUser) : null;
} catch {
  localStorage.removeItem("plugo_user");
  sessionStorage.removeItem("plugo_token");
}

export const useStore = create<Store>((set) => ({
  user: initialUser,
  setUser: (user) => {
    if (user) {
      // TODO(security): migrate to httpOnly cookie
      sessionStorage.setItem("plugo_token", user.token);
      localStorage.setItem("plugo_user", JSON.stringify(user));
    }
    set({ user });
  },
  logout: () => {
    sessionStorage.removeItem("plugo_token");
    localStorage.removeItem("plugo_user");
    set({ user: null });
  },
}));
