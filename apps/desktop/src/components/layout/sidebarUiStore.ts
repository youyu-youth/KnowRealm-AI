import { create } from "zustand";

/** 主壳侧边栏的 DOM id：标题栏切换按钮以 aria-controls 指向它。 */
export const APP_SIDEBAR_ID = "app-sidebar";
export const SIDEBAR_MIN_WIDTH = 64;
export const SIDEBAR_MAX_WIDTH = 360;

type SidebarUiState = {
  /** 折叠态只属于当前窗口会话，不落 settings.json：重启回落到展开。 */
  collapsed: boolean;
  width: number | null;
  setWidth: (width: number) => void;
  toggleSidebar: () => void;
};

/** 当前窗口的侧栏布局：Toggle 与拖拽宽度独立，重启恢复响应式默认宽度。 */
export const useSidebarUiStore = create<SidebarUiState>((set) => ({
  collapsed: false,
  width: null,
  setWidth: (width) =>
    set({
      width: Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width)),
    }),
  toggleSidebar: () => set((state) => ({ collapsed: !state.collapsed })),
}));
