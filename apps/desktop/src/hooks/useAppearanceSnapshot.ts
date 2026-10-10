import { useSyncExternalStore } from "react";

export const APPEARANCE_CHANGED_EVENT = "knowrealm:appearance-changed";

export function appearanceSnapshot(): string {
  const root = document.documentElement;
  return `${root.classList.contains("dark")}:${root.dataset.theme ?? ""}`;
}

function subscribeAppearance(onChange: () => void): () => void {
  window.addEventListener(APPEARANCE_CHANGED_EVENT, onChange);
  return () => window.removeEventListener(APPEARANCE_CHANGED_EVENT, onChange);
}

// 仅订阅视觉状态，供计算样式消费方刷新；不包含业务状态或组件身份。
export function useAppearanceSnapshot(): string {
  return useSyncExternalStore(subscribeAppearance, appearanceSnapshot);
}
