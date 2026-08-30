use std::error::Error;

use tauri::{
    App, AppHandle, Emitter, Manager,
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
};

const EXIT_REQUESTED_EVENT: &str = "desktop://exit-requested";
const SHOW_MENU_ID: &str = "show";
const EXIT_MENU_ID: &str = "exit";

pub fn setup(app: &mut App) -> Result<(), Box<dyn Error>> {
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

    Ok(())
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

fn show_and_focus<E>(
    show: impl FnOnce() -> Result<(), E>,
    focus: impl FnOnce() -> Result<(), E>,
) -> Result<(), E> {
    show()?;
    focus()
}

#[tauri::command]
pub fn exit_application(app: AppHandle) -> Result<(), String> {
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::cell::Cell;

    use super::show_and_focus;

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
