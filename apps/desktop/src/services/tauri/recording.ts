import { invoke } from "@tauri-apps/api/core";

export function setRecordingKeepAwake(enabled: boolean): Promise<void> {
  return invoke("set_recording_keep_awake", { enabled });
}

export function hideWindowTemporarily(milliseconds = 5_000): Promise<void> {
  return invoke("hide_window_temporarily", { milliseconds });
}
