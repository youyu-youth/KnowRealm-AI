import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import { openPath } from "@tauri-apps/plugin-opener";

/**
 * 学习资产 Markdown 导出的 Tauri 边界封装：系统保存对话框、UTF-8 文本写入与按需打开。
 * 路径始终来自用户在保存对话框中的显式选择，不拼接 shell 命令。
 */
export function chooseMarkdownSavePath(
  defaultPath: string,
): Promise<string | null> {
  return save({
    defaultPath,
    filters: [{ name: "Markdown", extensions: ["md"] }],
  });
}

export function writeMarkdownFile(
  path: string,
  contents: string,
): Promise<void> {
  return writeTextFile(path, contents);
}

export function openExportedFile(path: string): Promise<void> {
  return openPath(path);
}
