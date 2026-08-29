mod lifecycle;
mod power;
mod sidecar;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state == tauri_plugin_global_shortcut::ShortcutState::Pressed {
                        lifecycle::handle_shortcut(app);
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .setup(|app| {
            let lifecycle_state = lifecycle::setup(app)?;
            app.manage(lifecycle_state);
            let state = sidecar::start(app.handle())?;
            app.manage(state);
            app.manage(power::PowerState::start());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar::get_sidecar_config,
            power::set_recording_keep_awake,
            hide_window_temporarily,
            lifecycle::get_desktop_lifecycle_status,
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
