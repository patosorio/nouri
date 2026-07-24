import { create } from "zustand";

interface UiState {
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
}

/** Minimal client UI state — server data lives in TanStack Query. */
export const useUiStore = create<UiState>((set) => ({
  rightPanelOpen: false,
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
}));
