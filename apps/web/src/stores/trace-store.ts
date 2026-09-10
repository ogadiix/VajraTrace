/**
 * Zustand store for trace state management.
 */

import { create } from "zustand";

interface TraceState {
  currentTraceId: string | null;
  status: string | null;
  isLoading: boolean;
  error: string | null;
  setTraceId: (id: string) => void;
  setStatus: (status: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useTraceStore = create<TraceState>((set) => ({
  currentTraceId: null,
  status: null,
  isLoading: false,
  error: null,
  setTraceId: (id) => set({ currentTraceId: id }),
  setStatus: (status) => set({ status }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  reset: () =>
    set({
      currentTraceId: null,
      status: null,
      isLoading: false,
      error: null,
    }),
}));
