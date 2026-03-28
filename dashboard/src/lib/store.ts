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

// Restore user from localStorage on load
let initialUser = null;
try {
  const savedUser = localStorage.getItem("plugo_user");
  initialUser = savedUser ? JSON.parse(savedUser) : null;
} catch {
  localStorage.removeItem("plugo_user");
  localStorage.removeItem("plugo_token");
}

export const useStore = create<Store>((set) => ({
  user: initialUser,
  setUser: (user) => {
    if (user) {
      localStorage.setItem("plugo_token", user.token);
      localStorage.setItem("plugo_user", JSON.stringify(user));
    }
    set({ user });
  },
  logout: () => {
    localStorage.removeItem("plugo_token");
    localStorage.removeItem("plugo_user");
    set({ user: null });
  },
}));
