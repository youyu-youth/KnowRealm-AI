import { isTauri } from "@tauri-apps/api/core";
import type { UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { disable, enable } from "@tauri-apps/plugin-autostart";
import type { components } from "@knowrealm/api-types";

export type CloseBehaviorPreference =
  components["schemas"]["PreferencesOut"]["close_behavior"];

export type CloseBehaviorRuntimeOptions = {
  getBehavior: () => CloseBehaviorPreference | null;
  onExitRequested: () => void;
};

// 挂载一次，每次关窗经 getBehavior 读取当前策略，偏好切换无需重挂。
// TRAY=preventClose+hide；EXIT=preventClose+收敛 safeExit（确认后退出）；
// null（偏好未载入）不拦截，走 onCloseRequested 基座默认 destroy 即直接退出。
export function mountCloseBehavior(
  options: CloseBehaviorRuntimeOptions,
): Promise<UnlistenFn> {
  const window = getCurrentWindow();
  return window.onCloseRequested((event) => {
    const behavior = options.getBehavior();
    if (behavior !== "TRAY" && behavior !== "EXIT") return;
    event.preventDefault();
    if (behavior === "TRAY") {
      void window.hide();
    } else {
      options.onExitRequested();
    }
  });
}

// 写 OS 启动项；非桌面环境（浏览器 dev）无操作，偏好持久化照常。
export async function setAutostart(enabled: boolean): Promise<void> {
  if (!isTauri()) return;
  if (enabled) {
    await enable();
  } else {
    await disable();
  }
}
