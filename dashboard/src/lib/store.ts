import { create } from "zustand";

type Site = {
  id: string;
  name: string;
  url: string;
  token: string;
  llm_provider: string;
  llm_model: string;
  primary_color: string;
  greeting: string;
};

type User = {
  username: string;
  role: string;
  token: string;
};

type Store = {
  currentSite: Site | null;
  setCurrentSite: (site: Site | null) => void;
  user: User | null;
  setUser: (user: User | null) => void;
  logout: () => void;
};

// Restore user from localStorage on load
const savedUser = localStorage.getItem("plugo_user");
const initialUser = savedUser ? JSON.parse(savedUser) : null;

export const useStore = create<Store>((set) => ({
  currentSite: null,
  setCurrentSite: (site) => set({ currentSite: site }),
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
