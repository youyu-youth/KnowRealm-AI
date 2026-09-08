import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { relaunch } from "@tauri-apps/plugin-process";
import type { UiLanguage } from "@/i18n/language";

export const isDesktopLifecycleAvailable = isTauri;

export function listenExitRequested(handler: () => void): Promise<UnlistenFn> {
  return listen("desktop://exit-requested", handler);
}

export function exitApplication() {
  return invoke<void>("exit_application");
}

// 界面语言变更后通知壳层重建托盘菜单（显示/退出 ↔ Show/Exit）；非桌面环境无托盘，无操作。
export async function syncTrayLanguage(language: UiLanguage): Promise<void> {
  if (!isTauri()) return;
  await invoke<void>("rebuild_tray_menu", { language });
}

export function relaunchApplication() {
  return relaunch();
}
