import { invoke } from "@tauri-apps/api/core";

// desktop.json 只经壳 command 暴露当前路径，不进入 sidecar HTTP 契约。
export function getDataDirectory(): Promise<string> {
  return invoke<string>("get_data_directory");
}

export function openDataDirectory(): Promise<void> {
  return invoke("open_data_directory");
}
