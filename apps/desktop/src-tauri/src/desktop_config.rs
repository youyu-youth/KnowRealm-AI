use serde::{Deserialize, Serialize};
use std::{
    fs, io,
    path::{Path, PathBuf},
};

const FILE_NAME: &str = "desktop.json";

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct DesktopConfig {
    pub data_dir: PathBuf,
    pub onboarded: bool,
}

pub fn load_or_repair(config_dir: &Path, default_data_dir: &Path) -> DesktopConfig {
    let fallback = DesktopConfig {
        data_dir: default_data_dir.to_path_buf(),
        onboarded: false,
    };
    let path = config_dir.join(FILE_NAME);

    match fs::read(&path)
        .ok()
        .and_then(|contents| serde_json::from_slice::<DesktopConfig>(&contents).ok())
        .filter(|config| config.data_dir.is_absolute())
    {
        Some(config) => config,
        None => {
            if let Err(error) = write(config_dir, &fallback) {
                eprintln!("failed to write {}: {error}", path.display());
            }
            fallback
        }
    }
}

pub fn write(config_dir: &Path, config: &DesktopConfig) -> io::Result<()> {
    fs::create_dir_all(config_dir)?;
    let contents = serde_json::to_vec_pretty(config)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    fs::write(config_dir.join(FILE_NAME), contents)
}

#[cfg(test)]
mod tests {
    use super::{DesktopConfig, load_or_repair, write};
    use std::fs;

    fn test_root() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "knowrealm-desktop-config-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn valid_config_round_trips() {
        let root = test_root();
        let config_dir = root.join("config");
        let data_dir = root.join("data");
        let default_data_dir = root.join("default");
        let expected = DesktopConfig {
            data_dir: data_dir.clone(),
            onboarded: true,
        };

        write(&config_dir, &expected).unwrap();

        assert_eq!(load_or_repair(&config_dir, &default_data_dir), expected);
        assert_eq!(
            serde_json::from_slice::<DesktopConfig>(
                &fs::read(config_dir.join("desktop.json")).unwrap()
            )
            .unwrap(),
            expected
        );

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_corrupt_or_invalid_config_falls_back_and_rewrites_default() {
        for contents in [
            None,
            Some(b"not json".as_slice()),
            Some(br#"{"data_dir":"relative","onboarded":true}"#),
        ] {
            let root = test_root();
            let config_dir = root.join("config");
            let default_data_dir = root.join("default");
            if let Some(contents) = contents {
                fs::create_dir_all(&config_dir).unwrap();
                fs::write(config_dir.join("desktop.json"), contents).unwrap();
            }

            let actual = load_or_repair(&config_dir, &default_data_dir);

            assert_eq!(
                actual,
                DesktopConfig {
                    data_dir: default_data_dir,
                    onboarded: false,
                }
            );
            assert_eq!(
                serde_json::from_slice::<DesktopConfig>(
                    &fs::read(config_dir.join("desktop.json")).unwrap()
                )
                .unwrap(),
                actual
            );
            fs::remove_dir_all(root).unwrap();
        }
    }
}
