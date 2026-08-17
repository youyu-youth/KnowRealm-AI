use std::error::Error;
use std::ffi::OsString;
use std::io;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use getrandom::fill;
use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::{ShellExt, process::CommandChild};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use std::process::{Command, Stdio};

const LOOPBACK: &str = "127.0.0.1";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SidecarConfig {
    pub base_url: String,
    pub token: String,
}

pub struct SidecarState {
    config: SidecarConfig,
    child: Mutex<Option<CommandChild>>,
}

pub fn allocate_loopback_port() -> io::Result<u16> {
    // ponytail: releasing the OS-selected port leaves a tiny TOCTOU window;
    // pass an inherited socket only if real collision evidence appears.
    let listener = TcpListener::bind((LOOPBACK, 0))?;
    Ok(listener.local_addr()?.port())
}

pub fn launch_token() -> io::Result<String> {
    let mut bytes = [0_u8; 32];
    fill(&mut bytes).map_err(|error| io::Error::other(error.to_string()))?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

pub fn start(app: &AppHandle) -> Result<SidecarState, Box<dyn Error>> {
    let port = allocate_loopback_port()?;
    let token = launch_token()?;
    let data_dir = app.path().home_dir()?.join("KnowRealm");
    let (program, working_dir) = sidecar_program()?;
    let args = [
        OsString::from("-m"),
        OsString::from("app.server"),
        OsString::from("--port"),
        OsString::from(port.to_string()),
        OsString::from("--token"),
        OsString::from(&token),
        OsString::from("--data-dir"),
        data_dir.into_os_string(),
    ];
    let (mut events, child) = app
        .shell()
        .command(program)
        .current_dir(working_dir)
        .args(args)
        .spawn()?;
    tauri::async_runtime::spawn(async move { while events.recv().await.is_some() {} });

    if let Err(error) = wait_until_ready(port) {
        stop_process(child);
        return Err(Box::new(error));
    }
    Ok(SidecarState {
        config: SidecarConfig {
            base_url: format!("http://{LOOPBACK}:{port}"),
            token,
        },
        child: Mutex::new(Some(child)),
    })
}

fn wait_until_ready(port: u16) -> io::Result<()> {
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&address.into(), Duration::from_millis(100)).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(50));
    }
    Err(io::Error::new(
        io::ErrorKind::TimedOut,
        "sidecar startup timed out",
    ))
}

#[cfg(debug_assertions)]
fn sidecar_program() -> io::Result<(PathBuf, PathBuf)> {
    let backend = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../backend");
    let python = backend.join(if cfg!(target_os = "windows") {
        "./.venv/Scripts/python.exe"
    } else {
        "./.venv/bin/python"
    });
    Ok((python, backend))
}

#[cfg(not(debug_assertions))]
fn sidecar_program() -> io::Result<(PathBuf, PathBuf)> {
    let executable_dir = std::env::current_exe()?
        .parent()
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("desktop executable has no parent directory"))?;
    let executable = executable_dir.join(if cfg!(target_os = "windows") {
        "knowrealm-sidecar.exe"
    } else {
        "knowrealm-sidecar"
    });
    Ok((executable, executable_dir))
}

#[tauri::command]
pub fn get_sidecar_config(state: State<'_, SidecarState>) -> Result<SidecarConfig, &'static str> {
    Ok(state.config.clone())
}

impl SidecarState {
    pub fn stop(&self) {
        if let Ok(mut child) = self.child.lock()
            && let Some(child) = child.take()
        {
            stop_process(child);
        }
    }
}

#[cfg(target_os = "windows")]
fn stop_process(child: CommandChild) {
    let pid = child.pid().to_string();
    let mut command = Command::new("taskkill");
    command
        .args(["/PID", &pid, "/T", "/F"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(0x0800_0000);
    let _ = command.status();
    let _ = child.kill();
}

#[cfg(not(target_os = "windows"))]
fn stop_process(child: CommandChild) {
    let _ = child.kill();
}

#[cfg(test)]
mod tests {
    use super::{allocate_loopback_port, launch_token};

    #[test]
    fn allocates_random_port_and_unique_launch_tokens() {
        let port = allocate_loopback_port().expect("loopback port");
        let first = launch_token().expect("first token");
        let second = launch_token().expect("second token");

        assert!(port > 0);
        assert_eq!(first.len(), 64);
        assert_ne!(first, second);
    }
}
