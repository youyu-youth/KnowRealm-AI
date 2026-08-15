

## 工具(tools)使用习惯

- 在探索或检索代码库时，优先使用 codegraph 相关工具来探索或检索代码
- 当需要爬取网页数据的时候，你可以使用firecrawl 相关工具来进行爬取
- 当需要操作浏览器的时候，你可以使用playwright 工具来进行操作
- 技术文档查询时，适用context7 tools 即可

## Agent skills

### Issue tracker

议题以本地 markdown 文件跟踪于 `.scratch/<feature-slug>/`。见 `docs/agents/issue-tracker.md`。

### Triage labels

使用五个默认规范角色标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。
