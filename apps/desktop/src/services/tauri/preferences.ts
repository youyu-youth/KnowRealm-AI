import { isTauri } from "@tauri-apps/api/core";
import type { UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { disable, enable } from "@tauri-apps/plugin-autostart";
import {
  isRegistered,
  register,
  unregister,
} from "@tauri-apps/plugin-global-shortcut";
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

// ———— 速记快捷键：注册点在前端，经 global-shortcut JS API（Rust 侧注册与事件链已删） ————

let quickNoteHandler: (() => void) | null = null;
let activeQuickNoteShortcut: string | null = null;
let quickNoteMountInFlight: {
  shortcut: string;
  promise: Promise<boolean>;
} | null = null;

// global-shortcut 回调在按下与释放各触发一次，只响应按下。
function fireQuickNote(event: { state: "Pressed" | "Released" }) {
  if (event.state === "Pressed") quickNoteHandler?.();
}

// 启动挂载：按偏好注册速记快捷键，返回是否注册成功（shortcut_available 直接可知）。
// 偏好未载入（null）不注册；改键成功后偏好缓存刷新触发的重复挂载经 isRegistered 去重；
// 挂载在途期间若改键已完成，则撤销本次注册（新键已由改键流程接管）。
export async function mountQuickNoteShortcut(
  shortcut: string | null,
  onTriggered: () => void,
): Promise<boolean> {
  quickNoteHandler = onTriggered;
  if (shortcut === null) return false;
  if (activeQuickNoteShortcut === shortcut) return true;
  if (quickNoteMountInFlight?.shortcut === shortcut)
    return quickNoteMountInFlight.promise;
  const promise = (async () => {
    if (!isTauri()) return false;
    if (await isRegistered(shortcut)) {
      activeQuickNoteShortcut = shortcut;
      return true;
    }
    try {
      await register(shortcut, fireQuickNote);
    } catch {
      return false;
    }
    if (
      activeQuickNoteShortcut !== null &&
      activeQuickNoteShortcut !== shortcut
    ) {
      await unregister(shortcut).catch(() => undefined);
      return true;
    }
    activeQuickNoteShortcut = shortcut;
    return true;
  })();
  quickNoteMountInFlight = { shortcut, promise };
  try {
    return await promise;
  } finally {
    if (quickNoteMountInFlight?.promise === promise)
      quickNoteMountInFlight = null;
  }
}

export type QuickNoteRebindResult =
  | { ok: true }
  | { ok: false; reason: "conflict" | "persist-failed" | "failed" };

// 改键时序：试注册新键 → 注销旧键 → 持久化；任一步失败回滚到旧键并如实返回原因。
// 非桌面环境无 OS 注册可动，等价于只持久化（沿 setAutostart 的浏览器豁免）。
export async function rebindQuickNoteShortcut(
  next: string,
  persist: () => Promise<unknown>,
): Promise<QuickNoteRebindResult> {
  if (activeQuickNoteShortcut === next) return { ok: true };
  if (!isTauri()) {
    try {
      await persist();
    } catch {
      return { ok: false, reason: "persist-failed" };
    }
    activeQuickNoteShortcut = next;
    return { ok: true };
  }
  try {
    await register(next, fireQuickNote);
  } catch {
    return { ok: false, reason: "conflict" };
  }
  // 注册成功后再读旧键：若挂载恰在途，其落定的键也纳入注销范围。
  const previous = activeQuickNoteShortcut;
  if (previous !== null && previous !== next) {
    try {
      await unregister(previous);
    } catch {
      await unregister(next).catch(() => undefined);
      return { ok: false, reason: "failed" };
    }
  }
  activeQuickNoteShortcut = next;
  try {
    await persist();
  } catch {
    await unregister(next).catch(() => undefined);
    if (previous !== null) {
      try {
        await register(previous, fireQuickNote);
      } catch {
        return { ok: false, reason: "failed" };
      }
    }
    activeQuickNoteShortcut = previous;
    return { ok: false, reason: "persist-failed" };
  }
  return { ok: true };
}
