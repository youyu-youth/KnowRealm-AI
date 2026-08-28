use std::error::Error;

use serde::Serialize;
use tauri::{
    App, AppHandle, Emitter, Manager, Window, WindowEvent,
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
};
use tauri_plugin_global_shortcut::GlobalShortcutExt;

const SHORTCUT: &str = "Ctrl+Alt+N";
const OPEN_QUICK_NOTE_EVENT: &str = "desktop://open-quick-note";
const EXIT_REQUESTED_EVENT: &str = "desktop://exit-requested";
const SHOW_MENU_ID: &str = "show";
const EXIT_MENU_ID: &str = "exit";

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopLifecycleStatus {
    shortcut_available: bool,
}

pub fn setup(app: &mut App) -> Result<DesktopLifecycleStatus, Box<dyn Error>> {
    let shortcut_available = match app.global_shortcut().register(SHORTCUT) {
        Ok(()) => true,
        Err(error) => {
            eprintln!("global shortcut registration failed: {error}");
            false
        }
    };

    let show = MenuItem::with_id(app, SHOW_MENU_ID, "显示", true, None::<&str>)?;
    let exit = MenuItem::with_id(app, EXIT_MENU_ID, "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &exit])?;
    let mut tray = TrayIconBuilder::new()
        .menu(&menu)
        .show_menu_on_left_click(true)
        .tooltip("KnowRealm")
        .on_menu_event(|app, event| match event.id().as_ref() {
            SHOW_MENU_ID => show_main_window(app),
            EXIT_MENU_ID => {
                show_main_window(app);
                if let Err(error) = app.emit(EXIT_REQUESTED_EVENT, ()) {
                    eprintln!("exit request event failed: {error}");
                }
            }
            _ => {}
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;

    Ok(DesktopLifecycleStatus { shortcut_available })
}

pub fn handle_shortcut(app: &AppHandle) {
    show_main_window(app);
    if let Err(error) = app.emit(OPEN_QUICK_NOTE_EVENT, ()) {
        eprintln!("quick note event failed: {error}");
    }
}

pub fn handle_window_event(window: &Window, event: &WindowEvent) {
    if let WindowEvent::CloseRequested { api, .. } = event
        && should_hide_on_close(window.label())
    {
        api.prevent_close();
        if let Err(error) = window.hide() {
            eprintln!("main window hide failed: {error}");
        }
    }
}

fn show_main_window(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        eprintln!("main window is unavailable");
        return;
    };
    if let Err(error) = show_and_focus(|| window.show(), || window.set_focus()) {
        eprintln!("main window show or focus failed: {error}");
    }
}

fn should_hide_on_close(label: &str) -> bool {
    label == "main"
}

fn show_and_focus<E>(
    show: impl FnOnce() -> Result<(), E>,
    focus: impl FnOnce() -> Result<(), E>,
) -> Result<(), E> {
    show()?;
    focus()
}

#[tauri::command]
pub fn get_desktop_lifecycle_status(
    state: tauri::State<'_, DesktopLifecycleStatus>,
) -> Result<DesktopLifecycleStatus, String> {
    Ok(state.inner().clone())
}

#[tauri::command]
pub fn exit_application(app: AppHandle) -> Result<(), String> {
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::cell::Cell;

    use super::{should_hide_on_close, show_and_focus};

    #[test]
    fn close_policy_only_hides_main_window() {
        assert!(should_hide_on_close("main"));
        assert!(!should_hide_on_close("settings"));
    }

    #[test]
    fn restore_policy_shows_before_focusing() {
        let shown = Cell::new(false);
        let focused = Cell::new(false);

        show_and_focus(
            || {
                shown.set(true);
                Ok::<(), ()>(())
            },
            || {
                assert!(shown.get());
                focused.set(true);
                Ok::<(), ()>(())
            },
        )
        .unwrap();

        assert!(focused.get());
    }
}
