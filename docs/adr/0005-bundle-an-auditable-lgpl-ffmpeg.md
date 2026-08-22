# 随桌面应用分发可审计的 LGPL ffmpeg

音频处理不得依赖用户 PATH 或系统预装工具；桌面安装包通过 Tauri `externalBin` 携带关闭 GPL/nonfree 组件的 LGPL-compatible ffmpeg。构建来源、版本、配置、SHA-256 和许可证必须锁定并随包可查；ffprobe 仅用于测试，除非实现证明运行时无法由 ffmpeg 或容器解析取得所需元数据。项目自身采用何种开源许可证是独立的仓库级决策，不由音频功能代替决定。
