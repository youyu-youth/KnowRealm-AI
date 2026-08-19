import { invoke } from "@tauri-apps/api/core";

export type SidecarConfig = {
  baseUrl: string;
  token: string;
};

let configPromise: Promise<SidecarConfig> | undefined;

export function getSidecarConfig(): Promise<SidecarConfig> {
  configPromise ??= invoke<SidecarConfig>("get_sidecar_config").catch(
    (error: unknown) => {
      configPromise = undefined;
      throw error;
    },
  );
  return configPromise;
}
