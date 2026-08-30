import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";

// desktop.json 只经壳 command 暴露当前路径，不进入 sidecar HTTP 契约。
export function getDataDirectory(): Promise<string> {
  return invoke<string>("get_data_directory");
}

export function openDataDirectory(): Promise<void> {
  return invoke("open_data_directory");
}

export function changeDataDirectory(newPath: string): Promise<void> {
  return invoke("change_data_directory", { newDir: newPath });
}

export function chooseDataDirectory(title: string): Promise<string | null> {
  return open({ directory: true, multiple: false, title });
}

export function chooseImportArchive(title: string): Promise<string | null> {
  return open({
    multiple: false,
    title,
    filters: [{ name: "KnowRealm 导出包", extensions: ["zip"] }],
  });
}

// 记录导入意图并停 sidecar；重启（dev 手动 / 生产 relaunch）后壳带 --import-archive 拉起。
export function importFromArchive(archivePath: string): Promise<void> {
  return invoke("import_from_archive", { archivePath });
}

export type MigrationProgress = {
  copiedBytes: number;
  totalBytes: number;
};

export function listenMigrationProgress(
  handler: (progress: MigrationProgress) => void,
): Promise<UnlistenFn> {
  return listen<MigrationProgress>(
    "desktop://data-dir-migration-progress",
    (event) => handler(event.payload),
  );
}
