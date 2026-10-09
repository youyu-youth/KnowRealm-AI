import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

export function getDesktopWindow() {
  return isTauri() ? getCurrentWindow() : null;
}
