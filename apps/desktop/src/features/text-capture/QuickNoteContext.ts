import { createContext } from "react";

export const QuickNoteContext = createContext<(() => void) | null>(null);
