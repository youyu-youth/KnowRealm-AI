import { create } from "zustand";

/** 主壳侧边栏的 DOM id：标题栏切换按钮以 aria-controls 指向它。 */
export const APP_SIDEBAR_ID = "app-sidebar";

type SidebarUiState = {
  /** 折叠态只属于当前窗口会话，不落 settings.json：重启回落到展开。 */
  collapsed: boolean;
  toggleSidebar: () => void;
};

/** 侧边栏折叠状态：AppShell 消费，窗口标题栏切换。 */
export const useSidebarUiStore = create<SidebarUiState>((set) => ({
  collapsed: false,
  toggleSidebar: () => set((state) => ({ collapsed: !state.collapsed })),
}));
