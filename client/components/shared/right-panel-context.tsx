"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface RightPanelOptions {
  /** Panel width in px. Chat mockup: 320. Meal planner recipe panel: 360. */
  width?: number;
}

interface RightPanelContextValue {
  rightPanel: ReactNode | null;
  rightPanelWidth: number;
  setRightPanel: (node: ReactNode | null, options?: RightPanelOptions) => void;
}

const DEFAULT_WIDTH = 320;

const RightPanelContext = createContext<RightPanelContextValue | null>(null);

export function RightPanelProvider({ children }: { children: ReactNode }) {
  const [rightPanel, setRightPanelState] = useState<ReactNode | null>(null);
  const [rightPanelWidth, setRightPanelWidth] = useState(DEFAULT_WIDTH);

  const setRightPanel = useCallback(
    (node: ReactNode | null, options?: RightPanelOptions) => {
      setRightPanelState(node);
      setRightPanelWidth(options?.width ?? DEFAULT_WIDTH);
    },
    [],
  );

  const value = useMemo(
    () => ({ rightPanel, rightPanelWidth, setRightPanel }),
    [rightPanel, rightPanelWidth, setRightPanel],
  );

  return (
    <RightPanelContext.Provider value={value}>
      {children}
    </RightPanelContext.Provider>
  );
}

export function useRightPanel(): RightPanelContextValue {
  const ctx = useContext(RightPanelContext);
  if (!ctx) {
    throw new Error("useRightPanel must be used within RightPanelProvider");
  }
  return ctx;
}
