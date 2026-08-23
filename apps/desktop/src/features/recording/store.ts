import { create } from "zustand";

type RecordingUiState = {
  startOpen: boolean;
  activeSessionId: string | null;
  title: string;
  courseId: string | null;
  confirmAbandon: boolean;
  busy: boolean;
  error: string | null;
  elapsedMs: number;
  setStartOpen: (startOpen: boolean) => void;
  setActiveSessionId: (activeSessionId: string | null) => void;
  setTitle: (title: string) => void;
  setCourseId: (courseId: string | null) => void;
  setConfirmAbandon: (confirmAbandon: boolean) => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
  setElapsedMs: (elapsedMs: number) => void;
  resetDraft: () => void;
  reset: () => void;
};

const initialState = {
  startOpen: false,
  activeSessionId: null,
  title: "",
  courseId: null,
  confirmAbandon: false,
  busy: false,
  error: null,
  elapsedMs: 0,
};

export const useRecordingUiStore = create<RecordingUiState>((set) => ({
  ...initialState,
  setStartOpen: (startOpen) => set({ startOpen }),
  setActiveSessionId: (activeSessionId) => set({ activeSessionId }),
  setTitle: (title) => set({ title }),
  setCourseId: (courseId) => set({ courseId }),
  setConfirmAbandon: (confirmAbandon) => set({ confirmAbandon }),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error }),
  setElapsedMs: (elapsedMs) => set({ elapsedMs }),
  resetDraft: () => set({ title: "", courseId: null }),
  reset: () => set(initialState),
}));
