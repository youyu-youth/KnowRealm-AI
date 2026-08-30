import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export const isDesktopLifecycleAvailable = isTauri;

export function listenExitRequested(handler: () => void): Promise<UnlistenFn> {
  return listen("desktop://exit-requested", handler);
}

export function exitApplication() {
  return invoke<void>("exit_application");
}
