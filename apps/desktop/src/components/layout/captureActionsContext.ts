import { createContext } from "react";

export type CaptureAction =
  "capture.note" | "capture.paste" | "capture.import" | "capture.record";

export const CaptureActionsContext = createContext<
  ((action: CaptureAction) => void) | null
>(null);
