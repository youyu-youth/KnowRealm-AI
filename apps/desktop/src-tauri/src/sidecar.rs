use std::error::Error;
use std::ffi::OsString;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use getrandom::fill;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_opener::OpenerExt;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

use crate::data_migration;
use crate::desktop_config;
use crate::pending_import;

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
    data_dir: PathBuf,
    child: Mutex<Option<Child>>,
}

pub fn launch_token() -> io::Result<String> {
    let mut bytes = [0_u8; 32];
    fill(&mut bytes).map_err(|error| io::Error::other(error.to_string()))?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

pub fn start(app: &AppHandle) -> Result<SidecarState, Box<dyn Error>> {
    let token = launch_token()?;
    let (config_dir, config) = resolve_desktop_config(app)?;
    let data_dir = config.data_dir;
    // 一次性消费待导入意图：文件删除先于 sidecar 拉起，导入失败不会循环重试。
    let mut import_archive = pending_import::take(&config_dir).map(|pending| pending.archive);
    if let Some(archive) = &import_archive
        && !archive.is_file()
    {
        eprintln!(
            "pending import archive is missing, starting normally: {}",
            archive.display()
        );
        import_archive = None;
    }
    let ffmpeg = ffmpeg_program()?;
    if !ffmpeg.is_file() {
        return Err(Box::new(io::Error::new(
            io::ErrorKind::NotFound,
            "bundled ffmpeg is missing",
        )));
    }
    let (program, working_dir) = sidecar_program()?;
    let mut args = vec![
        OsString::from("-m"),
        OsString::from("app.server"),
        OsString::from("--port"),
        OsString::from("0"),
        OsString::from("--token"),
        OsString::from(&token),
        OsString::from("--data-dir"),
        data_dir.clone().into_os_string(),
        OsString::from("--ffmpeg"),
        ffmpeg.into_os_string(),
    ];
    if let Some(archive) = import_archive {
        args.push(OsString::from("--import-archive"));
        args.push(archive.into_os_string());
    }
    let mut command = Command::new(program);
    command
        .current_dir(working_dir)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(target_os = "windows")]
    command.creation_flags(0x0800_0000);
    let mut child = command.spawn()?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| io::Error::other("sidecar stdout is unavailable"))?;
    let mut stderr = child
        .stderr
        .take()
        .ok_or_else(|| io::Error::other("sidecar stderr is unavailable"))?;
    let (event_tx, event_rx) = mpsc::channel();
    thread::spawn(move || {
        for line in BufReader::new(stdout).split(b'\n') {
            let Ok(line) = line else { break };
            if event_tx.send(line).is_err() {
                break;
            }
        }
    });
    thread::spawn(move || {
        let _ = io::copy(&mut stderr, &mut io::stderr());
    });

    let port = match wait_for_bound_port(&event_rx) {
        Ok(port) => port,
        Err(error) => {
            stop_process(child);
            return Err(Box::new(error));
        }
    };
    if let Err(error) = wait_until_ready(port, &token) {
        stop_process(child);
        return Err(Box::new(error));
    }
    Ok(SidecarState {
        config: SidecarConfig {
            base_url: format!("http://{LOOPBACK}:{port}"),
            token,
        },
        data_dir,
        child: Mutex::new(Some(child)),
    })
}

fn wait_for_bound_port(events: &mpsc::Receiver<Vec<u8>>) -> io::Result<u16> {
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
            Ok(bytes) => {
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

#[tauri::command]
pub fn get_data_directory(state: State<'_, SidecarState>) -> Result<PathBuf, &'static str> {
    Ok(state.data_dir.clone())
}

#[tauri::command]
pub fn open_data_directory(app: AppHandle, state: State<'_, SidecarState>) -> Result<(), String> {
    app.opener()
        .open_path(state.data_dir.to_string_lossy(), None::<&str>)
        .map_err(|error| error.to_string())
}

/// 记录导入意图并停 sidecar（释放数据目录锁）；重启由前端触发（同迁移流程）。
/// 新进程启动时 sidecar::start 消费 pending-import.json 并带 --import-archive 拉起。
#[tauri::command]
pub fn import_from_archive(
    app: AppHandle,
    state: State<'_, SidecarState>,
    archive_path: PathBuf,
) -> Result<(), String> {
    if !archive_path.is_file() {
        return Err(format!("导出包不存在：{}", archive_path.display()));
    }
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| error.to_string())?;
    pending_import::write(&config_dir, &archive_path).map_err(|error| error.to_string())?;
    state.stop();
    Ok(())
}

/// 停止 sidecar → 同盘 rename / 跨盘 copy+删源（进度事件）→ 写回 desktop.json。
/// 顺序要点：copy 路径在删源之前写配置——任一环节失败都能靠重启恢复到一致状态。
/// 重启由前端在成功返回后触发（tauri-plugin-process relaunch）。
#[tauri::command]
pub async fn change_data_directory(
    app: AppHandle,
    state: State<'_, SidecarState>,
    new_dir: PathBuf,
) -> Result<(), data_migration::MigrationError> {
    let old_dir = state.data_dir.clone();
    let created_target = data_migration::prepare_target(&old_dir, &new_dir)?;

    // 校验通过才停 sidecar：目录无效时应用照常可用
    state.stop();

    let progress_app = app.clone();
    let migration_source = old_dir.clone();
    let migration_target = new_dir.clone();
    let moved = tauri::async_runtime::spawn_blocking(move || {
        data_migration::move_data(&migration_source, &migration_target, &mut |copied, total| {
            let _ = progress_app.emit(
                data_migration::MIGRATION_PROGRESS_EVENT,
                data_migration::MigrationProgress {
                    copied_bytes: copied,
                    total_bytes: total,
                },
            );
        })
    })
    .await
    .unwrap_or_else(|error| {
        Err(data_migration::MigrationError::Migration(std::io::Error::other(
            error.to_string(),
        )))
    });

    // 移动阶段失败：原目录仍完好（copy 失败不动源、rename 原子），清理目标半成品
    let outcome = match moved {
        Ok(outcome) => outcome,
        Err(error) => {
            data_migration::cleanup_target(&new_dir, created_target);
            return Err(error);
        }
    };

    let (config_dir, mut config) = resolve_desktop_config(&app).map_err(|error| {
        data_migration::MigrationError::ConfigWrite(std::io::Error::other(error.to_string()))
    })?;
    config.data_dir = new_dir.clone();
    if let Err(error) = desktop_config::write(&config_dir, &config) {
        // copy 路径此刻源目录未删：回退清理后重启即可恢复旧目录
        if outcome == data_migration::MoveOutcome::Copied {
            data_migration::cleanup_target(&new_dir, created_target);
        }
        return Err(data_migration::MigrationError::ConfigWrite(error));
    }

    data_migration::remove_source(&old_dir, outcome)?;
    Ok(())
}

fn resolve_desktop_config(
    app: &AppHandle,
) -> Result<(PathBuf, desktop_config::DesktopConfig), tauri::Error> {
    let default_data_dir = app.path().home_dir()?.join("KnowRealm");
    let config_dir = app.path().app_config_dir()?;
    let config = desktop_config::load_or_repair(&config_dir, &default_data_dir);
    Ok((config_dir, config))
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
fn stop_process(mut child: Child) {
    let pid = child.id().to_string();
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
fn stop_process(mut child: Child) {
    let _ = child.kill();
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::mpsc;
    use std::thread;

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
            .send(b"KNOWREALM_SIDECAR_PORT=43127\r".to_vec())
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
