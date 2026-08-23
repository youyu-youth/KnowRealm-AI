use std::sync::mpsc;
use std::thread;

enum Command {
    Set(bool, mpsc::SyncSender<Result<(), String>>),
}

pub struct PowerState {
    sender: mpsc::Sender<Command>,
}

impl PowerState {
    pub fn start() -> Self {
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            while let Ok(Command::Set(enabled, reply)) = receiver.recv() {
                let _ = reply.send(set_thread_awake(enabled));
            }
            let _ = set_thread_awake(false);
        });
        Self { sender }
    }

    fn set(&self, enabled: bool) -> Result<(), String> {
        let (reply, result) = mpsc::sync_channel(1);
        self.sender
            .send(Command::Set(enabled, reply))
            .map_err(|_| "录音电源管理线程不可用".to_owned())?;
        result
            .recv()
            .map_err(|_| "未收到录音电源管理结果".to_owned())?
    }
}

#[tauri::command]
pub fn set_recording_keep_awake(
    enabled: bool,
    state: tauri::State<'_, PowerState>,
) -> Result<(), String> {
    state.set(enabled)
}

#[cfg(target_os = "windows")]
fn set_thread_awake(enabled: bool) -> Result<(), String> {
    use windows_sys::Win32::System::Power::{
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED, SetThreadExecutionState,
    };

    let flags = if enabled {
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    } else {
        ES_CONTINUOUS
    };
    // SAFETY: SetThreadExecutionState has no pointer arguments; flags are documented constants.
    if unsafe { SetThreadExecutionState(flags) } == 0 {
        Err(std::io::Error::last_os_error().to_string())
    } else {
        Ok(())
    }
}

#[cfg(not(target_os = "windows"))]
fn set_thread_awake(_enabled: bool) -> Result<(), String> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::PowerState;

    #[test]
    fn keep_awake_can_be_enabled_and_released() {
        let state = PowerState::start();
        state.set(true).expect("enable keep-awake");
        state.set(false).expect("release keep-awake");
    }
}
