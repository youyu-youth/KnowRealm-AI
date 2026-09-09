// 后端错误契约（ADR-0017）：错误响应形如 {detail, code, params?}，detail 中文原文保留。
// 码表命中的错误按界面语言取 errors 命名空间译文并插值 params；未命中回显 detail 原文。
// ApiError 构造与 SSE error 事件共用此单一入口，所有 error.message 展示点零改动受益。
// 直接用 i18next 默认单例（@/i18n init 配置的就是它）：避免顶层导入 @/i18n（其初始化读
// window），node 环境的纯逻辑测试导入本链路不炸；未初始化时一律回显原文。
import i18next from "i18next";

export function apiErrorMessage(
  code: string | undefined,
  detail: string,
  params: Record<string, unknown> | undefined,
): string {
  if (!code || !i18next.isInitialized) return detail;
  const key = `errors.${code}`;
  if (!i18next.exists(key)) return detail;
  return i18next.t(key, { ...params });
}
