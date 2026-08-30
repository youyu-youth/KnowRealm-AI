// 数据目录迁移（change_data_directory）在移动目录前会停掉 sidecar 且不再拉起，
// 此后后端不可恢复、应用必须重启。该标记记录这一事实：
// 安全退出据此跳过录音状态检查——后端已不存在，无录音可保护，
// 否则"无法确认录音状态"会把退出永久卡死，应用只能靠任务管理器结束。
let restartPending = false;

export function markRestartPending(): void {
  restartPending = true;
}

export function isRestartPending(): boolean {
  return restartPending;
}

// 仅供测试在用例间复位模块级状态。
export function resetRestartPending(): void {
  restartPending = false;
}
