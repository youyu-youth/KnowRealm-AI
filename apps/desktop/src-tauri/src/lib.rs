mod data_migration;
mod desktop_config;
mod lifecycle;
mod power;
mod sidecar;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .setup(|app| {
            lifecycle::setup(app)?;
            let state = sidecar::start(app.handle())?;
            app.manage(state);
            app.manage(power::PowerState::start());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar::get_sidecar_config,
            sidecar::get_data_directory,
            sidecar::open_data_directory,
            sidecar::change_data_directory,
            power::set_recording_keep_awake,
            hide_window_temporarily,
            lifecycle::exit_application,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit)
            && let Some(state) = app_handle.try_state::<sidecar::SidecarState>()
        {
            state.stop();
        }
    });
}

#[tauri::command]
fn hide_window_temporarily(window: tauri::WebviewWindow, milliseconds: u64) -> Result<(), String> {
    window.hide().map_err(|error| error.to_string())?;
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(milliseconds));
        let _ = window.show();
    });
    Ok(())
}
