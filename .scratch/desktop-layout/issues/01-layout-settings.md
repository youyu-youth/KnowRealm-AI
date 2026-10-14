# 布局偏好与响应式顶部导航

Status: ready-for-human

- [x] 偏好 API、JSON 默认/坏值/合并及重建应用后的恢复，真实临时数据目录与 ASGI API（70 项后端测试）。
- [x] 契约生成物、外观与布局选项、错误/重试，双语与相关自动化（70 项前端测试）。
- [x] 共用导航，顶部溢出菜单、近期课程及档案/设置可达，保留页面与侧栏会话状态（相关自动化与隔离真实 API 的浏览器检查）。
- [x] 相关回归、范围检查、构建及浏览器四主题、字号/英文/窄窗检查（32 组视口/焦点模拟，见 validation.md）。
- [ ] 真实 Tauri/WebView2、Windows 系统缩放及真实桌面进程重启（不可由浏览器替身代勾）。

验证路径：设置 RadioGroup → 既有 useSavePreference → PUT preferences → config/settings.json → GET/prepareAppearance → AppShell 与 WindowTitleBar。前端以 MSW 替换 IPC/API 边界；后端 API 使用隔离数据目录及真实文件保存，重建应用后 GET；真实模型无关。

人工验收：在设置外观与布局选择顶部导航，访问所有已实现页面并打开近期课程、档案和设置；缩小窗口并切英文/大字号，确认溢出项可以通过更多导航访问；切回侧栏确认宽度、折叠及页面状态保持；退出进程重启检查恢复；保存失败检查错误与原布局。
