use tauri::AppHandle;

use crate::sidecar;

/// 首启判定：desktop.json 的 onboarded 字段（ADR-0013）。
/// 文件缺失/损坏回退默认配置时 onboarded=false，即视为首启进向导。
#[tauri::command]
pub fn get_onboarding_state(app: AppHandle) -> Result<bool, String> {
    let (_, config) = sidecar::resolve_desktop_config(&app).map_err(|error| error.to_string())?;
    Ok(config.onboarded)
}

/// 向导完成（含全部跳过）时写入 onboarded=true；此后无"重新运行"入口。
#[tauri::command]
pub fn complete_onboarding(app: AppHandle) -> Result<(), String> {
    let (config_dir, mut config) =
        sidecar::resolve_desktop_config(&app).map_err(|error| error.to_string())?;
    config.onboarded = true;
    crate::desktop_config::write(&config_dir, &config).map_err(|error| error.to_string())
}
