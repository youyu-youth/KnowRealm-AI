import { invoke } from "@tauri-apps/api/core";
import { openPath } from "@tauri-apps/plugin-opener";

// desktop.json 只经壳 command 暴露当前路径，不进入 sidecar HTTP 契约。
export function getDataDirectory(): Promise<string> {
  return invoke<string>("get_data_directory");
}

export function openDataDirectory(path: string): Promise<void> {
  return openPath(path);
}
