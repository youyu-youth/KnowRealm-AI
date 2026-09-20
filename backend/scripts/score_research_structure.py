"""研究会话黄金集「固定结构完整率」评分脚本（research-session-v1 工单 02）。

用法：先按 `docs/evaluation/research-session-golden-set.md` §4 复跑流程采集
回答（每题一个 .md/.txt 文件），再执行：

    uv run python -m scripts.score_research_structure <回答文件或目录...>

对每个文件断言五节标题逐字齐全、顺序正确、无增删（`## ` 二级标题中不得出现
五节之外的其他小节），输出逐文件判定与整体通过率。门禁阈值与四指标口径见
黄金集文档 §3；本脚本只覆盖机械可判的结构完整率，其余三指标按 rubric 人工评。
"""

import sys
from pathlib import Path

from app.modules.agent.context import CHAT_RESEARCH_SECTION_TITLES

EXIT_PASS = 0
EXIT_FAIL = 1


def collect_answers(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            files.extend(p for p in sorted(path.iterdir()) if p.suffix.lower() in {".md", ".txt"})
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"路径不存在: {raw}")
    if not files:
        raise SystemExit("没有可评分的回答文件（支持 .md/.txt）")
    return files


def score(text: str) -> tuple[bool, str]:
    """返回 (是否完整, 原因)：五个 `## ` 二级标题须逐字匹配且相对顺序严格递增，
    出现五节之外 / 顺序错乱 / 重复的二级标题都判不完整（`###` 以下不校验）。"""
    headings = [line.strip() for line in text.splitlines() if line.strip().startswith("## ")]
    expected = [f"## {title}" for title in CHAT_RESEARCH_SECTION_TITLES]
    matched = 0
    for heading in headings:
        if matched < len(expected) and heading == expected[matched]:
            matched += 1
        elif heading in expected:
            return False, f"标题顺序或重复错误：「{heading}」"
        else:
            return False, f"出现五节之外的二级标题：「{heading}」"
    if matched < len(expected):
        return False, f"缺少标题：{'、'.join(expected[matched:])}"
    return True, "五节齐全且顺序正确"


def main() -> int:
    files = collect_answers(sys.argv[1:])
    passed = 0
    for path in files:
        ok, reason = score(path.read_text(encoding="utf-8"))
        passed += int(ok)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {path.name}: {reason}")
    total = len(files)
    rate = passed / total
    print(f"固定结构完整率：{passed}/{total} = {rate:.0%}（门禁 ≥90%）")
    return EXIT_PASS if rate >= 0.9 else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
