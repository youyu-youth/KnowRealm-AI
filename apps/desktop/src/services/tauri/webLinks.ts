import { openUrl } from "@tauri-apps/plugin-opener";

/**
 * 外部链接的 Tauri 边界封装：经系统默认应用打开（能力面只放行 http/https）。
 * URL 始终来自后端落库的网络引用条目，不拼接 shell 命令。
 */
export function openWebUrl(url: string): Promise<void> {
  return openUrl(url);
}
