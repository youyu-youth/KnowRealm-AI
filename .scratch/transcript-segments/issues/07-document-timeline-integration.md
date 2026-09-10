# 07 — 文档记录时间轴集成补票：接入 document-segments + 标记列泛化

**What to build（票 05 集成缺陷修复）:** 用户实测刚导入的 md 文档（06-结构化输出）转写页只有纯文本、无任何时间轴 UI。取证定位：文档导入定稿只写 document_segments（块级 510 行、offset 与全文闭合），transcript_segments=0——行级分片对文档只有启动回填/编辑重切两个来源（且粒度按行拆非块拆）；票 05 前端只消费 transcript/segments 端点，票 03 专门建的 document-segments 姊妹端点（带 page_no）从未接线 → 新导入文档（未重启）两源一空一满，前端回落纯文本。全库佐证：最新文档 ds>0 且 ts=0；docker 为重启后回填的行级 ts（平均 37 字、孤立 `>` 成行）+ 块级 ds 并存；票 03 前旧文档只有行级 ts。

**Spec 参考:** 同目录 `../spec.md`（故事 11「PDF 按页分片带页码、DOCX/txt/md 按内容块分片，引用能落到页码或块」——本票把该能力接入转写页时间轴）。

**Status:** done

- [x] 前端数据源分派：`capture_type=DOCUMENT_IMPORT` → document-segments（块级、导入即有、无需重启）；ds 为空（票 03 前旧文档）→ 回落 transcript-segments（行级）；两源皆空 → 纯文本（粘贴/速记）；非文档记录维持 transcript-segments、永不拉文档块
- [x] 时间轴标记列泛化：音频时间戳（mm:ss / h:mm:ss）｜ PDF 页码（page_no，i18n `第N页`/`Page N`，落 spec 故事 11）｜ 全表无任何标记来源时退为淡色块序号列（01/02/…，序号非时间标记、回应「看不到时间轴元素」的感知问题）；无标记行保留占位列维持基线；引用定位机制复用（多命中取首 + mark 内联高亮 + 命中行标记升级徽章 + 滚动；quote 为全文真实行、行必属于某块 → 文档记录跳转必中）
- [x] 后端配套：`realign_for_edit` 编辑保存同事务删除该记录 document_segments（content 已改则块界与 offset 全失效；前端随之回落行级重切结果）+ service 测试（编辑后 ds 清零、ts 重建）
- [x] 失效链路：RecordDetailPage.invalidateRecord / 保存 onSuccess / 409 载入最新版本 补 documentSegments key
- [x] i18n：`record.detail.transcript.pageLabel` zh/en 同步
- [x] 测试：TranscriptPanel 12→16 用例（md 块时间轴序号列、PDF 页码徽章 + 引用定位、旧文档 ds 空回落行级、文档编辑保存后 ds 清零回落）；既有 fixture capture_type 改 AUDIO_IMPORT（ts 用例语义不变）；后端 control_plane 7→8
- [x] 门禁：前端 vitest 390/391（唯一失败「今日页空态」为基线存量问题，与本票无关）+ tsc + prettier；后端 422 passed + ruff + pyright；openapi 零漂移（无 schema 变更）

**明确不做:** docker 等已回填行级 ts 数据保留（UI 优先 ds，无害）；MULTI_SOURCE 记录文档部分并入拼接时间轴（留后续）；旧文档重建块级分片（源文件不保证在）。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 重启应用后打开「06-结构化输出」等新导入文档的转写页：看到块级行式时间轴（左侧块序号列、行间细分隔线）；无需再重启一次
- [ ] 导入 PDF 后转写页左列显示页码；chat 引用角标点击后跳转定位到块并高亮（页码徽章）
