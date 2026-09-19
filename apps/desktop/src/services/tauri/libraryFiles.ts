import { revealItemInDir } from "@tauri-apps/plugin-opener";

import { getDataDirectory } from "@/services/tauri/dataDirectory";

/**
 * 资料快照的 Tauri 边界封装：在系统资源管理器中显示数据目录内的快照文件。
 * relPath 始终来自后端落库的 local_path（数据目录相对 posix 路径），
 * 不接收任意绝对路径。
 */
export async function revealLibrarySnapshot(relPath: string): Promise<void> {
  const root = (await getDataDirectory()).replace(/[/\\]+$/, "");
  await revealItemInDir(`${root}/${relPath}`);
}
