// OneDrive 检测（工单 06）：路径分段以 OneDrive 开头（含 "OneDrive - 组织" 目录名），
// 或含 "%OneDrive%" 环境变量前缀，即视为同步范围。
export function looksLikeOneDrivePath(path: string): boolean {
  return path.split(/[\\/]+/).some((segment) => {
    const name = segment.toLowerCase();
    return name.startsWith("onedrive") || name.includes("%onedrive%");
  });
}
