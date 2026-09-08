use std::error::Error;

use tauri::{
    App, AppHandle, Emitter, Manager,
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
};

const EXIT_REQUESTED_EVENT: &str = "desktop://exit-requested";
const TRAY_ID: &str = "main-tray";
const SHOW_MENU_ID: &str = "show";
const EXIT_MENU_ID: &str = "exit";

// 菜单项 id 恒定（show/exit），事件处理器随首次构建注册，换语言只换标签不换协议。
fn tray_labels(language: &str) -> Option<(&'static str, &'static str)> {
    match language {
        "zh" => Some(("显示", "退出")),
        "en" => Some(("Show", "Exit")),
        _ => None,
    }
}

fn build_tray_menu(app: &AppHandle, language: &str) -> Result<Menu<tauri::Wry>, tauri::Error> {
    let (show_label, exit_label) = tray_labels(language).unwrap_or(("显示", "退出"));
    let show = MenuItem::with_id(app, SHOW_MENU_ID, show_label, true, None::<&str>)?;
    let exit = MenuItem::with_id(app, EXIT_MENU_ID, exit_label, true, None::<&str>)?;
    Menu::with_items(app, &[&show, &exit])
}

pub fn setup(app: &mut App) -> Result<(), Box<dyn Error>> {
    let menu = build_tray_menu(app.handle(), "zh")?;
    let mut tray = TrayIconBuilder::with_id(TRAY_ID)
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

// 前端切换界面语言时调用：按菜单 id 原地换菜单，托盘本体与事件协议不动。
#[tauri::command]
pub fn rebuild_tray_menu(app: AppHandle, language: String) -> Result<(), String> {
    if tray_labels(&language).is_none() {
        return Err(format!("unsupported tray language: {language}"));
    }
    let tray = app
        .tray_by_id(TRAY_ID)
        .ok_or_else(|| "tray icon is unavailable".to_string())?;
    let menu = build_tray_menu(&app, &language).map_err(|error| error.to_string())?;
    tray.set_menu(Some(menu)).map_err(|error| error.to_string())
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
