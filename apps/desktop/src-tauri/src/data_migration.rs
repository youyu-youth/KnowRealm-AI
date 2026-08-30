use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::Serialize;

pub const MIGRATION_PROGRESS_EVENT: &str = "desktop://data-dir-migration-progress";

/// 前端错误协议：Display 输出 `CODE` 或 `CODE: io 明细`，经 command 的
/// serde::Serialize 以字符串传回，前端按 `": "` 切分映射中文文案。
#[derive(Debug, thiserror::Error)]
pub enum MigrationError {
    #[error("DATA_DIRECTORY_SAME")]
    SameDirectory,
    #[error("DATA_DIRECTORY_NESTED")]
    NestedDirectory,
    #[error("DATA_DIRECTORY_NOT_EMPTY")]
    NotEmpty,
    /// 移动阶段失败：原目录完好，可清理目标后重启重试。
    #[error("DATA_DIRECTORY_MIGRATION_FAILED: {0}")]
    Migration(io::Error),
    /// 配置写回失败：迁移中断（copy 路径已回退目标；rename 路径数据在新目录）。
    #[error("DATA_DIRECTORY_CONFIG_WRITE_FAILED: {0}")]
    ConfigWrite(io::Error),
    /// 删源失败（仅 copy 路径）：desktop.json 已指向完整新目录，重启即生效。
    #[error("DATA_DIRECTORY_SOURCE_CLEANUP_FAILED: {0}")]
    SourceCleanupFailed(io::Error),
}

impl Serialize for MigrationError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

#[derive(Clone, Copy, PartialEq)]
pub enum MoveOutcome {
    /// 同盘 rename：源目录已整体移走，无删源收尾。
    Renamed,
    /// 跨盘 copy：源目录完好，remove_source 收尾。
    Copied,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MigrationProgress {
    pub copied_bytes: u64,
    pub total_bytes: u64,
}

/// 校验并准备目标目录，返回是否由本次创建（决定失败清理时是否连目录一起删）。
/// 不存在的路径自动创建；已存在的必须是空目录。
pub fn prepare_target(old_dir: &Path, new_dir: &Path) -> Result<bool, MigrationError> {
    let old_dir = normalize(old_dir);
    let new_dir = normalize(new_dir);
    if same_path(&old_dir, &new_dir) {
        return Err(MigrationError::SameDirectory);
    }
    if is_within(&new_dir, &old_dir) || is_within(&old_dir, &new_dir) {
        return Err(MigrationError::NestedDirectory);
    }
    if new_dir.exists() {
        if !new_dir.is_dir() {
            return Err(MigrationError::Migration(io::Error::new(
                io::ErrorKind::InvalidInput,
                "target exists and is not a directory",
            )));
        }
        let is_empty = fs::read_dir(&new_dir)
            .map_err(MigrationError::Migration)?
            .next()
            .is_none();
        if !is_empty {
            return Err(MigrationError::NotEmpty);
        }
        Ok(false)
    } else {
        fs::create_dir_all(&new_dir).map_err(MigrationError::Migration)?;
        Ok(true)
    }
}

/// 移动阶段：同盘 rename 一步到位；跨盘（rename 报 NOT_SAME_DEVICE/EXDEV）退化为
/// 带进度上报 (copied, total) 字节的整目录复制。失败时原目录保持原样。
pub fn move_data(
    source: &Path,
    target: &Path,
    progress: &mut dyn FnMut(u64, u64),
) -> Result<MoveOutcome, MigrationError> {
    // Windows 的 MoveFileEx 不能以目录替换已存在目录（ERROR_ACCESS_DENIED）；
    // prepare_target 已保证目标（若存在）为空目录，摘掉空壳再 rename。
    if target.exists() {
        fs::remove_dir(target).map_err(MigrationError::Migration)?;
    }
    match fs::rename(source, target) {
        Ok(()) => Ok(MoveOutcome::Renamed),
        Err(error) if is_cross_device(&error) => {
            copy_all(source, target, progress)?;
            Ok(MoveOutcome::Copied)
        }
        Err(error) => Err(MigrationError::Migration(error)),
    }
}

/// 移动收尾：copy 路径在 desktop.json 写回成功之后删除源目录。
pub fn remove_source(source: &Path, outcome: MoveOutcome) -> Result<(), MigrationError> {
    if outcome == MoveOutcome::Renamed {
        return Ok(());
    }
    fs::remove_dir_all(source).map_err(MigrationError::SourceCleanupFailed)
}

/// 清理迁移失败后的目标残留。自建目录连壳删除；既有空目录只删搬入的内容；
/// 目标已不存在时静默（前序步骤可能已摘掉空壳）。
pub fn cleanup_target(target: &Path, created_by_us: bool) {
    if !target.exists() {
        return;
    }
    let result = if created_by_us {
        fs::remove_dir_all(target)
    } else {
        remove_dir_contents(target)
    };
    if let Err(error) = result {
        eprintln!(
            "failed to clean up partial migration target {}: {error}",
            target.display()
        );
    }
}

fn is_cross_device(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::CrossesDevices
        || matches!(error.raw_os_error(), Some(17 | 18)) // 17=Windows NOT_SAME_DEVICE, 18=Unix EXDEV
}

fn copy_all(
    source: &Path,
    target: &Path,
    progress: &mut dyn FnMut(u64, u64),
) -> Result<(), MigrationError> {
    let total = dir_size(source).map_err(MigrationError::Migration)?;
    progress(0, total);
    let mut copied = 0_u64;
    copy_tree(source, target, &mut copied, total, progress)?;
    Ok(())
}

fn copy_tree(
    source: &Path,
    target: &Path,
    copied: &mut u64,
    total: u64,
    progress: &mut dyn FnMut(u64, u64),
) -> Result<(), MigrationError> {
    fs::create_dir_all(target).map_err(MigrationError::Migration)?;
    for entry in fs::read_dir(source).map_err(MigrationError::Migration)? {
        let entry = entry.map_err(MigrationError::Migration)?;
        let entry_target = target.join(entry.file_name());
        let metadata = entry.metadata().map_err(MigrationError::Migration)?;
        if metadata.is_dir() {
            copy_tree(&entry.path(), &entry_target, copied, total, progress)?;
        } else {
            fs::copy(entry.path(), &entry_target).map_err(MigrationError::Migration)?;
            *copied += metadata.len();
            progress(*copied, total);
        }
    }
    Ok(())
}

fn dir_size(dir: &Path) -> io::Result<u64> {
    let mut total = 0_u64;
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let metadata = entry.metadata()?;
        if metadata.is_dir() {
            total += dir_size(&entry.path())?;
        } else {
            total += metadata.len();
        }
    }
    Ok(total)
}

fn remove_dir_contents(dir: &Path) -> io::Result<()> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        if entry.metadata()?.is_dir() {
            fs::remove_dir_all(entry.path())?;
        } else {
            fs::remove_file(entry.path())?;
        }
    }
    Ok(())
}

/// canonicalize 解析大小写与链接后剥掉 `\\?\` verbatim 前缀，让前后比较口径一致。
fn normalize(path: &Path) -> PathBuf {
    let canonical = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    strip_verbatim_prefix(&canonical)
}

fn strip_verbatim_prefix(path: &Path) -> PathBuf {
    let text = path.as_os_str().to_string_lossy();
    if let Some(rest) = text.strip_prefix(r"\\?\UNC\") {
        PathBuf::from(format!(r"\\{rest}"))
    } else if let Some(rest) = text.strip_prefix(r"\\?\") {
        PathBuf::from(rest)
    } else {
        path.to_path_buf()
    }
}

#[cfg(windows)]
fn os_eq(a: &std::ffi::OsStr, b: &std::ffi::OsStr) -> bool {
    a.eq_ignore_ascii_case(b)
}

#[cfg(not(windows))]
fn os_eq(a: &std::ffi::OsStr, b: &std::ffi::OsStr) -> bool {
    a == b
}

fn same_path(a: &Path, b: &Path) -> bool {
    os_eq(a.as_os_str(), b.as_os_str())
}

/// 前缀组件逐一比较（而非字符串前缀），避免 `D:\KnowRealm2` 误判为 `D:\KnowRealm` 之内。
fn is_within(child: &Path, ancestor: &Path) -> bool {
    let mut child_components = child.components();
    let ancestor_matched = ancestor.components().all(|a| {
        child_components
            .next()
            .is_some_and(|c| os_eq(c.as_os_str(), a.as_os_str()))
    });
    ancestor_matched && child_components.next().is_some()
}

#[cfg(test)]
mod tests {
    use super::{
        MoveOutcome, MigrationError, cleanup_target, copy_all, is_cross_device, is_within,
        move_data, normalize, prepare_target, remove_source,
    };
    use std::fs;
    use std::io;
    use std::path::{Path, PathBuf};

    fn test_root() -> PathBuf {
        std::env::temp_dir().join(format!(
            "knowrealm-data-migration-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    fn write_tree(root: &Path, files: &[(&str, &str)]) {
        for (relative, contents) in files {
            let path = root.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, contents).unwrap();
        }
    }

    fn assert_tree_matches(dir: &Path, files: &[(&str, &str)]) {
        for (relative, contents) in files {
            assert_eq!(
                fs::read(dir.join(relative)).unwrap(),
                contents.as_bytes(),
                "content mismatch for {relative}"
            );
        }
        assert_eq!(
            count_entries(dir),
            files.len(),
            "unexpected extra entries in {dir:?}"
        );
    }

    fn count_entries(dir: &Path) -> usize {
        let mut count = 0;
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                count += count_entries(&path);
            } else {
                count += 1;
            }
        }
        count
    }

    #[test]
    fn same_volume_rename_moves_the_whole_directory() {
        let root = test_root();
        let source = root.join("old");
        let target = root.join("new");
        write_tree(&source, &[("knowrealm.db", "db"), ("files/a.txt", "a")]);

        move_data(&source, &target, &mut |_, _| {}).unwrap();

        assert!(!source.exists());
        assert_tree_matches(&target, &[("knowrealm.db", "db"), ("files/a.txt", "a")]);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rename_replaces_prepared_empty_target() {
        let root = test_root();
        let source = root.join("old");
        let target = root.join("new");
        write_tree(&source, &[("knowrealm.db", "db")]);
        // 模拟 command 主流程：prepare_target 先建出空目标
        assert!(prepare_target(&source, &target).unwrap());

        move_data(&source, &target, &mut |_, _| {}).unwrap();

        assert!(!source.exists());
        assert_tree_matches(&target, &[("knowrealm.db", "db")]);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn copy_all_reports_progress_then_remove_source_deletes_it() {
        let root = test_root();
        let source = root.join("old");
        let target = root.join("new");
        write_tree(
            &source,
            &[("knowrealm.db", "0123456789"), ("files/nested/b.txt", "bb")],
        );

        let mut events: Vec<(u64, u64)> = Vec::new();
        copy_all(&source, &target, &mut |copied, total| {
            events.push((copied, total));
        })
        .unwrap();
        remove_source(&source, MoveOutcome::Copied).unwrap();

        assert!(!source.exists());
        assert_tree_matches(
            &target,
            &[("knowrealm.db", "0123456789"), ("files/nested/b.txt", "bb")],
        );
        assert_eq!(events.first().map(|(copied, _)| *copied), Some(0));
        let total = events.first().unwrap().1;
        assert_eq!(total, 12);
        assert_eq!(events.last().unwrap().0, total);
        assert!(events.windows(2).all(|pair| pair[0].0 <= pair[1].0));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn prepare_target_creates_missing_and_accepts_existing_empty() {
        let root = test_root();
        let old_dir = root.join("old");
        fs::create_dir_all(&old_dir).unwrap();

        let missing = root.join("a/missing");
        assert!(prepare_target(&old_dir, &missing).unwrap());
        assert!(missing.is_dir());

        let existing_empty = root.join("existing-empty");
        fs::create_dir(&existing_empty).unwrap();
        assert!(!prepare_target(&old_dir, &existing_empty).unwrap());

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn prepare_target_rejects_same_nested_and_non_empty_targets() {
        let root = test_root();
        let old_dir = root.join("old");
        write_tree(&old_dir, &[("files/a.txt", "a")]);

        assert!(matches!(
            prepare_target(&old_dir, &old_dir),
            Err(MigrationError::SameDirectory)
        ));
        assert!(matches!(
            prepare_target(&old_dir, &old_dir.join("sub")),
            Err(MigrationError::NestedDirectory)
        ));
        assert!(matches!(
            prepare_target(&old_dir, &root),
            Err(MigrationError::NestedDirectory)
        ));
        // 大小写不同的同一目录（Windows 语义）
        #[cfg(windows)]
        assert!(matches!(
            prepare_target(&old_dir, &root.join("OLD")),
            Err(MigrationError::SameDirectory)
        ));

        let non_empty = root.join("non-empty");
        fs::create_dir_all(&non_empty).unwrap();
        fs::write(non_empty.join("stray.txt"), "x").unwrap();
        assert!(matches!(
            prepare_target(&old_dir, &non_empty),
            Err(MigrationError::NotEmpty)
        ));
        // 拒绝后原目录与候选目录都不动
        assert!(old_dir.join("files/a.txt").exists());
        assert!(non_empty.join("stray.txt").exists());

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn copy_failure_leaves_source_intact_and_target_cleanable() {
        use std::os::windows::fs::OpenOptionsExt;

        let root = test_root();
        let source = root.join("old");
        let target = root.join("new");
        write_tree(&source, &[("db/locked.db", "db"), ("files/a.txt", "a")]);
        // share_mode(0)：本句柄不开放任何共享 → fs::copy 读源即失败
        let lock = fs::OpenOptions::new()
            .write(true)
            .share_mode(0)
            .open(source.join("db/locked.db"))
            .unwrap();

        let result = copy_all(&source, &target, &mut |_, _| {});

        assert!(matches!(result, Err(MigrationError::Migration(_))));
        assert!(source.join("db/locked.db").exists());
        assert!(source.join("files/a.txt").exists());

        cleanup_target(&target, true);
        assert!(!target.exists());
        drop(lock);
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn delete_source_failure_keeps_complete_copy_and_reports_source_cleanup() {
        use std::os::windows::fs::OpenOptionsExt;

        let root = test_root();
        let source = root.join("old");
        let target = root.join("new");
        write_tree(&source, &[("db/open.db", "db"), ("files/a.txt", "a")]);
        // share_mode(1)=仅共享读：fs::copy 可读，但句柄不放行删除 → remove_source 失败
        let lock = fs::OpenOptions::new()
            .write(true)
            .share_mode(1)
            .open(source.join("db/open.db"))
            .unwrap();

        copy_all(&source, &target, &mut |_, _| {}).unwrap();
        let result = remove_source(&source, MoveOutcome::Copied);

        assert!(matches!(
            result,
            Err(MigrationError::SourceCleanupFailed(_))
        ));
        // 目标是唯一完整副本，必须保留；源中被锁文件残留属预期
        assert_tree_matches(
            &target,
            &[("db/open.db", "db"), ("files/a.txt", "a")],
        );
        drop(lock);
        fs::remove_dir_all(source).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn remove_source_is_noop_after_rename() {
        let root = test_root();
        let dir = root.join("kept");
        fs::create_dir_all(&dir).unwrap();

        remove_source(&dir, MoveOutcome::Renamed).unwrap();

        assert!(dir.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn cross_device_rename_error_falls_back_to_copy() {
        assert!(is_cross_device(&io::Error::from_raw_os_error(17)));
        assert!(is_cross_device(&io::Error::from_raw_os_error(18)));
        assert!(is_cross_device(&io::Error::new(
            io::ErrorKind::CrossesDevices,
            "exdev",
        )));
        assert!(!is_cross_device(&io::Error::from_raw_os_error(5)));
    }

    #[test]
    fn within_uses_component_prefix_not_text_prefix() {
        let ancestor = PathBuf::from("D:/KnowRealm");
        assert!(is_within(&PathBuf::from("D:/KnowRealm/sub"), &ancestor));
        assert!(!is_within(&PathBuf::from("D:/KnowRealm2"), &ancestor));
        #[cfg(windows)]
        assert!(is_within(&PathBuf::from("d:/knowrealm/SUB"), &ancestor));
        assert!(!is_within(&ancestor, &ancestor));
    }

    #[test]
    fn normalize_strips_verbatim_prefix_for_comparison() {
        #[cfg(windows)]
        {
            let verbatim = PathBuf::from(r"\\?\C:\Users\tester\KnowRealm");
            assert_eq!(
                normalize(&verbatim),
                PathBuf::from(r"C:\Users\tester\KnowRealm")
            );
        }
        let missing = PathBuf::from("/definitely/missing/path");
        assert_eq!(normalize(&missing), missing);
    }
}
