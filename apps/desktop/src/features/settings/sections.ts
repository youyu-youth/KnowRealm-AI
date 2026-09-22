export const SETTINGS_SECTIONS = [
  "profile",
  "ai",
  "appearance",
  "desktop",
  "general",
  "data",
  "automation",
  "operations",
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export function isSettingsSection(value: unknown): value is SettingsSection {
  return SETTINGS_SECTIONS.some((section) => section === value);
}
