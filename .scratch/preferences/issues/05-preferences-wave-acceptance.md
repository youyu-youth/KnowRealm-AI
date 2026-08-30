# 05 — 偏好设置总验收（真机人工）

**What to build:** 偏好设置全部票完成后收口：自动化门禁全绿，按 13 号功能计划九条验收标准**人工逐条执行**并回写勾选，自动化证据与真机验收分层记录、不互冒充。（验收线见 `.scratch/function-plans-introduction/13-preferences.md`，契约见 `.scratch/preferences/spec.md`）

**Blocked by:** 01、02、03、04 — 全部功能票

**Status:** deferred

- [ ] 自动化门禁全绿：后端 pytest（本机 `--basetemp=.pytest-tmp`）、前端 vitest + tsc --noEmit + eslint、cargo test、改动文件 prettier
- [ ] 真机人工逐条执行 13 号计划九条并回写：①深色三态即时生效 + SYSTEM 跟随 OS + 重启保持 ②字号 S/M/L 重启保持 ③改键新键生效旧键失效 + 冲突提示保旧键 ④关窗 TRAY/EXIT 即时切换 + EXIT 安全退出确认 ⑤自启真实写 OS ⑥窗口恢复 + 显示器拔除夹回 ⑦上次界面恢复 + 失效兜底 ⑧settings.json 持久化（缺键=默认、未知键保留、窗口几何豁免） ⑨quiz_last_count 双入口一致
- [ ] settings.json 实机抽查：手工核对各键落值、consent 键未被冲掉、窗口几何不在该文件
- [ ] 13 号功能计划验收项全勾并置 done（工单回写惯例）
