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

type Store = {
  currentSite: Site | null;
  setCurrentSite: (site: Site | null) => void;
};

export const useStore = create<Store>((set) => ({
  currentSite: null,
  setCurrentSite: (site) => set({ currentSite: site }),
}));
