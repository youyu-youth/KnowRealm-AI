use std::error::Error;
use std::ffi::OsString;
use std::io::{self, Read, Write};
use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
use std::path::PathBuf;
use std::sync::{Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use getrandom::fill;
use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::{
    ShellExt,
    process::{CommandChild, CommandEvent},
};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use std::process::{Command, Stdio};

const LOOPBACK: &str = "127.0.0.1";
const PORT_MARKER: &str = "KNOWREALM_SIDECAR_PORT=";
#[cfg(not(test))]
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);
#[cfg(test)]
const STARTUP_TIMEOUT: Duration = Duration::from_millis(200);

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

pub fn launch_token() -> io::Result<String> {
    let mut bytes = [0_u8; 32];
    fill(&mut bytes).map_err(|error| io::Error::other(error.to_string()))?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

pub fn start(app: &AppHandle) -> Result<SidecarState, Box<dyn Error>> {
    let token = launch_token()?;
    let data_dir = app.path().home_dir()?.join("KnowRealm");
    let ffmpeg = ffmpeg_program()?;
    if !ffmpeg.is_file() {
        return Err(Box::new(io::Error::new(
            io::ErrorKind::NotFound,
            "bundled ffmpeg is missing",
        )));
    }
    let (program, working_dir) = sidecar_program()?;
    let args = [
        OsString::from("-m"),
        OsString::from("app.server"),
        OsString::from("--port"),
        OsString::from("0"),
        OsString::from("--token"),
        OsString::from(&token),
        OsString::from("--data-dir"),
        data_dir.into_os_string(),
        OsString::from("--ffmpeg"),
        ffmpeg.into_os_string(),
    ];
    let (mut events, child) = app
        .shell()
        .command(program)
        .current_dir(working_dir)
        .args(args)
        .spawn()?;
    let (event_tx, event_rx) = mpsc::channel();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            if event_tx.send(event).is_err() {
                break;
            }
        }
    });

    let port = match wait_for_bound_port(&event_rx) {
        Ok(port) => port,
        Err(error) => {
            stop_process(child);
            return Err(Box::new(error));
        }
    };
    thread::spawn(move || while event_rx.recv().is_ok() {});

    if let Err(error) = wait_until_ready(port, &token) {
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

fn wait_for_bound_port(events: &mpsc::Receiver<CommandEvent>) -> io::Result<u16> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "sidecar did not report its bound port",
            ));
        }
        match events.recv_timeout(remaining) {
            Ok(CommandEvent::Stdout(bytes)) => {
                let Ok(line) = std::str::from_utf8(&bytes) else {
                    continue;
                };
                let Some(value) = line.strip_prefix(PORT_MARKER) else {
                    continue;
                };
                let port = value
                    .trim()
                    .parse::<u16>()
                    .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
                if port == 0 {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "sidecar reported port zero",
                    ));
                }
                return Ok(port);
            }
            Ok(CommandEvent::Error(error)) => return Err(io::Error::other(error)),
            Ok(CommandEvent::Terminated(payload)) => {
                return Err(io::Error::other(format!(
                    "sidecar terminated before startup: {:?}",
                    payload.code
                )));
            }
            Ok(_) => {}
            Err(mpsc::RecvTimeoutError::Timeout) => {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "sidecar did not report its bound port",
                ));
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err(io::Error::new(
                    io::ErrorKind::BrokenPipe,
                    "sidecar event stream closed before startup",
                ));
            }
        }
    }
}

fn wait_until_ready(port: u16, token: &str) -> io::Result<()> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    while Instant::now() < deadline {
        if health_is_ready(port, token).unwrap_or(false) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(50));
    }
    Err(io::Error::new(
        io::ErrorKind::TimedOut,
        "sidecar health check timed out",
    ))
}

fn health_is_ready(port: u16, token: &str) -> io::Result<bool> {
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let mut stream = TcpStream::connect_timeout(&address.into(), Duration::from_millis(100))?;
    stream.set_read_timeout(Some(Duration::from_millis(100)))?;
    stream.set_write_timeout(Some(Duration::from_millis(100)))?;
    write!(
        stream,
        "GET /api/health HTTP/1.1\r\nHost: {LOOPBACK}:{port}\r\nX-KnowRealm-Token: {token}\r\nConnection: close\r\n\r\n"
    )?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return Ok(false);
    };
    Ok(
        (headers.starts_with("HTTP/1.1 200 ") || headers.starts_with("HTTP/1.0 200 "))
            && body.trim() == r#"{"status":"ok"}"#,
    )
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

#[cfg(debug_assertions)]
fn ffmpeg_program() -> io::Result<PathBuf> {
    Ok(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("binaries/ffmpeg-x86_64-pc-windows-msvc.exe"),
    )
}

#[cfg(not(debug_assertions))]
fn ffmpeg_program() -> io::Result<PathBuf> {
    let executable_dir = std::env::current_exe()?
        .parent()
        .map(PathBuf::from)
        .ok_or_else(|| io::Error::other("desktop executable has no parent directory"))?;
    Ok(executable_dir.join(if cfg!(target_os = "windows") {
        "ffmpeg.exe"
    } else {
        "ffmpeg"
    }))
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
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::mpsc;
    use std::thread;

    use tauri_plugin_shell::process::CommandEvent;

    use super::{health_is_ready, launch_token, wait_for_bound_port, wait_until_ready};

    #[test]
    fn creates_unique_launch_tokens() {
        let first = launch_token().expect("first token");
        let second = launch_token().expect("second token");

        assert_eq!(first.len(), 64);
        assert_ne!(first, second);
    }

    #[test]
    fn reads_the_newline_terminated_port_reported_by_the_spawned_sidecar() {
        let (sender, receiver) = mpsc::channel();
        sender
            .send(CommandEvent::Stdout(
                b"KNOWREALM_SIDECAR_PORT=43127\r\n".to_vec(),
            ))
            .expect("port event");

        assert_eq!(
            wait_for_bound_port(&receiver).expect("reported port"),
            43127
        );
    }

    #[test]
    fn health_probe_sends_the_launch_token_and_checks_the_response() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).expect("health listener");
        let port = listener.local_addr().expect("health address").port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("health connection");
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                let mut chunk = [0_u8; 256];
                let size = stream.read(&mut chunk).expect("health request");
                assert!(size > 0, "health request ended before its headers");
                request.extend_from_slice(&chunk[..size]);
            }
            let request = std::str::from_utf8(&request).expect("utf8 request");
            assert!(request.contains("X-KnowRealm-Token: test-launch-token\r\n"));
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 15\r\nConnection: close\r\n\r\n{\"status\":\"ok\"}",
                )
                .expect("health response");
        });

        assert!(health_is_ready(port, "test-launch-token").expect("health probe"));
        server.join().expect("health server");
    }

    #[test]
    fn rejects_an_unverified_tcp_listener() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).expect("fake listener");
        let port = listener.local_addr().expect("fake address").port();

        assert!(wait_until_ready(port, "test-launch-token").is_err());
    }
}
