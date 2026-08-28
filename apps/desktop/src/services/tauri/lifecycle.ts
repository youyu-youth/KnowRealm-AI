import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export type DesktopLifecycleStatus = {
  shortcutAvailable: boolean;
};

export const isDesktopLifecycleAvailable = isTauri;

export function getDesktopLifecycleStatus() {
  return invoke<DesktopLifecycleStatus>("get_desktop_lifecycle_status");
}

export function listenOpenQuickNote(handler: () => void): Promise<UnlistenFn> {
  return listen("desktop://open-quick-note", handler);
}

export function listenExitRequested(handler: () => void): Promise<UnlistenFn> {
  return listen("desktop://exit-requested", handler);
}

export function exitApplication() {
  return invoke<void>("exit_application");
}
