# FFmpeg 随包依赖

- 固定版本：`n8.1.2-44-g7c533d0f86`（FFmpeg 8.1 分支）
- 发布：BtbN `autobuild-2026-08-21-13-40`，上游构建提交 `48576f1`
- 资产：`ffmpeg-n8.1.2-44-g7c533d0f86-win64-lgpl-shared-8.1.zip`
- 来源：<https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-08-21-13-40>
- SHA-256：`e30201900132c0e3da178c63c7dac65aa0a0dcd971779546ae964b86b47bd499`
- 许可证变体：LGPL shared；归档自带的 `LICENSE.txt` 随桌面包分发。
- 构建配置：完整输出见 [ffmpeg-buildconf.txt](./ffmpeg-buildconf.txt)；必须包含 shared/LGPL 变体，禁止替换为 GPL 构建。

`pnpm --filter @knowrealm/desktop prepare:ffmpeg` 下载固定资产、校验归档 SHA-256，并生成 Tauri `externalBin` 与运行 DLL。运行时只把该显式路径传给 sidecar；不得读取或回退到系统 `PATH`。
