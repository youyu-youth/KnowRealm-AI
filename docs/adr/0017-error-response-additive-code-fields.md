# 错误响应契约：γ′ 附加字段（detail + code + params?）

---
Status: accepted（2026-09-08，界面语言切换 plan 20 grill 定稿）
---

界面语言切换（PRD 界面语言/内容语言决策，spec 见 `.scratch/i18n-language-switch/spec.md`）要求英文界面下后端报错也显示英文。后端 200+ 处错误响应的 `detail` 是中文原文，前端若靠中文串匹配翻译则契约脆弱、随措辞改动即碎，需要一个稳定错误码。选型焦点：**在既有 `{"detail": ...}` 形状上附加字段（γ′），还是把错误响应整体替换为结构化码主体**。该选择满足难逆（全部消费端与文档生成的契约形状）、无上下文会困惑（为何 detail 仍是中文主字段）、真实权衡（契约纯度 vs 迁移成本）三条件，故落 ADR。

**决定**：γ′ 附加字段。错误响应统一为：

```json
{"detail": "请先配置 LLM Provider", "code": "LLM_PROVIDER_UNCONFIGURED"}
{"detail": "服务器内部错误（请求编号：…）", "code": "INTERNAL_ERROR", "params": {"request_id": "…"}}
```

- `detail` 中文原文**逐字保留**——后端既有 pytest 断言 detail 中文**零改动**（选型主因，384 项既有测试即回归网）。
- `code` 全部错误响应必有（含 422/500 通用码与框架级回退 `HTTP_ERROR`）；`params` 仅带动态值时出现（当前仅 500 的 `request_id`）。
- 实现载体：`CodedHTTPException`（`app/shared/errors.py`）+ 统一异常处理器；生产代码禁止 raise 裸 `HTTPException`（防线测试 `tests/test_error_code_guard.py`）。
- 翻译职责在前端：命中码按码表取译文并插值 params，未命中回显 detail 原文（错误码清单见 `docs/后端错误码清单.md`）。

## Considered Options

| 方案 | 结论 |
|------|------|
| **γ′ 附加字段** | **采纳**——detail 保留使既有测试零改动；旧客户端/脚本不受影响；翻译未命中时 detail 天然兜底 |
| 纯结构化替换（码为主体，detail 降级或移除） | 否决——全部错误响应形状变更，既有测试断言与前端错误处理需同步改写；契约纯度的收益不抵破坏面 |
| 后端按 Accept-Language 协商翻译 | 否决——后端不掌握界面语言状态，翻译职责错位；单用户本地优先场景引入语言协商属过度设计 |

## Consequences

- `detail` 中残存的旧 `CODE：中文` 前缀（chat / capture 模块的既有风格）**不清洗**——code 字段上线后前缀冗余但无害，清洗反而改动全部既有断言。
- 新增错误必须配码并同步错误码清单文档，防线测试拦截裸 raise；码名与清单的漂移靠人工纪律（清单为文档，非生成物）。
- 码名一经消费即冻结：改动码名等价于契约破坏性变更，只增不改。
