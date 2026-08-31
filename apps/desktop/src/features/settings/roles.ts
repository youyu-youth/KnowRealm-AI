// 角色枚举为设置页与首启向导共用：单一来源避免两处白名单漂移。
export const ROLE_KEYS = [
  "STUDENT",
  "DEVELOPER",
  "OFFICE_WORKER",
  "OTHER",
] as const;
export type RoleKey = (typeof ROLE_KEYS)[number];

export function isRoleKey(value: string): value is RoleKey {
  return (ROLE_KEYS as readonly string[]).includes(value);
}
