import { invoke } from "@tauri-apps/api/core";

import { isDesktopLifecycleAvailable } from "./lifecycle";

// 首启判定结果在会话内缓存：onboarded 只会 false→true 翻转（向导无重跑入口），
// 而根路由 beforeLoad 每次导航都会询问，缓存省去反复 IPC。
let cachedOnboarded: boolean | null = null;

export function isOnboardingRequired(): Promise<boolean> {
  if (!isDesktopLifecycleAvailable()) return Promise.resolve(false);
  if (cachedOnboarded !== null) return Promise.resolve(!cachedOnboarded);
  return invoke<boolean>("get_onboarding_state").then((onboarded) => {
    cachedOnboarded = onboarded;
    return !onboarded;
  });
}

export function completeOnboarding(): Promise<void> {
  return invoke("complete_onboarding").then(() => {
    cachedOnboarded = true;
  });
}

// 仅供测试在用例间复位模块级缓存。
export function resetOnboardingCacheForTests(): void {
  cachedOnboarded = null;
}
