use serde::{Deserialize, Serialize};
use std::{
    fs, io,
    path::{Path, PathBuf},
};

/// 跨重启传递导入意图：`import_from_archive` 写入，下次启动 `sidecar::start` 取走。
/// 与 desktop.json 同放 app_config_dir，但不属于 ADR-0013 的持久配置——一次性消费即删。
const FILE_NAME: &str = "pending-import.json";

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct PendingImport {
    pub archive: PathBuf,
}

pub fn write(config_dir: &Path, archive: &Path) -> io::Result<()> {
    fs::create_dir_all(config_dir)?;
    let contents = serde_json::to_vec_pretty(&PendingImport {
        archive: archive.to_path_buf(),
    })
    .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    fs::write(config_dir.join(FILE_NAME), contents)
}

/// 读取并删除待导入意图（一次性）；缺失/损坏一律返回 None 且不留文件。
pub fn take(config_dir: &Path) -> Option<PendingImport> {
    let path = config_dir.join(FILE_NAME);
    let pending = fs::read(&path)
        .ok()
        .and_then(|contents| serde_json::from_slice::<PendingImport>(&contents).ok());
    if let Err(error) = fs::remove_file(&path) {
        eprintln!("failed to remove {}: {error}", path.display());
    }
    pending
}

#[cfg(test)]
mod tests {
    use super::{PendingImport, take, write};
    use std::fs;

    fn test_root() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "knowrealm-pending-import-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn write_then_take_round_trips_and_consumes_the_file() {
        let root = test_root();
        let config_dir = root.join("config");
        let archive = root.join("export.zip");

        write(&config_dir, &archive).unwrap();

        assert_eq!(
            take(&config_dir),
            Some(PendingImport {
                archive: archive.clone()
            })
        );
        assert!(!config_dir.join("pending-import.json").exists());
        assert_eq!(take(&config_dir), None);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn corrupted_file_is_ignored_and_removed() {
        let root = test_root();
        let config_dir = root.join("config");
        fs::create_dir_all(&config_dir).unwrap();
        fs::write(config_dir.join("pending-import.json"), b"not json").unwrap();

        assert_eq!(take(&config_dir), None);
        assert!(!config_dir.join("pending-import.json").exists());
        fs::remove_dir_all(root).unwrap();
    }
}
