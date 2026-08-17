use std::error::Error;
use std::io;
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use getrandom::fill;
use serde::Serialize;
use tauri::{AppHandle, Manager, State};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

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
    child: Mutex<Child>,
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
    let mut command = Command::new(program);
    command
        .current_dir(working_dir)
        .args([
            "-m",
            "app.server",
            "--port",
            &port.to_string(),
            "--token",
            &token,
            "--data-dir",
        ])
        .arg(data_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    command.creation_flags(0x0800_0000);

    let mut child = command.spawn()?;
    wait_until_ready(&mut child, port)?;
    Ok(SidecarState {
        config: SidecarConfig {
            base_url: format!("http://{LOOPBACK}:{port}"),
            token,
        },
        child: Mutex::new(child),
    })
}

fn wait_until_ready(child: &mut Child, port: u16) -> io::Result<()> {
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    while Instant::now() < deadline {
        if let Some(status) = child.try_wait()? {
            return Err(io::Error::other(format!(
                "sidecar exited before startup: {status}"
            )));
        }
        if TcpStream::connect_timeout(&address.into(), Duration::from_millis(100)).is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(50));
    }
    stop_process(child);
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
        if let Ok(mut child) = self.child.lock() {
            stop_process(&mut child);
        }
    }
}

#[cfg(target_os = "windows")]
fn stop_process(child: &mut Child) {
    let pid = child.id().to_string();
    let mut command = Command::new("taskkill");
    command
        .args(["/PID", &pid, "/T", "/F"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .creation_flags(0x0800_0000);
    let _ = command.status();
    let _ = child.wait();
}

#[cfg(not(target_os = "windows"))]
fn stop_process(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
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
