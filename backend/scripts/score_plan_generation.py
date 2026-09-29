"""学习计划生成黄金集「排期合规 / 结构完整」评分脚本（第三阶段工单 02）。

用法：先按 `docs/evaluation/plan-generation-checklist.md` §3 采集草案（每题
一个 .json 采集文件，形态见 plan-generation-samples.md §2），再执行：

    uv run python -m scripts.score_plan_generation <采集文件或目录...>

对每个文件机械复算三件事（红线指标）：
1. 排期逐位等于确定性铺排（顺序 + 每日预算 + 首日锚定，与
   learning_plan.scheduling.pack_schedule 同源）；
2. 全部排期不超目标期限（无期限跳过该项）；
3. 结构完整：生产 Schema（PlanConfirmPayload）同口径校验 + 阶段 2~5
   （checklist §2 结构完整率；Schema 只保证非空不覆盖本项）。

输出逐文件判定与整体通过率（门禁 100%）；资料贴合度与理由可解释性按
checklist §2 rubric 人工评，本脚本不覆盖。
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.modules.agent.schemas import PlanConfirmPayload
from app.modules.learning_plan.scheduling import (
    DEFAULT_DAILY_MINUTES,
    ScheduleConstraints,
    ScheduleInfeasible,
    pack_schedule,
)

EXIT_PASS = 0
EXIT_FAIL = 1


def collect_cases(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            files.extend(p for p in sorted(path.iterdir()) if p.suffix.lower() == ".json")
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"路径不存在: {raw}")
    if not files:
        raise SystemExit("没有可评分的采集文件（支持 .json）")
    return files


def score(case: dict[str, Any]) -> tuple[bool, str]:
    goal = case.get("goal")
    plan = case.get("plan")
    if not isinstance(goal, dict) or not isinstance(plan, dict):
        return False, "缺少 goal / plan 结构"

    # 结构完整：生产 Schema 同口径（model_validate_json 与 LLM 输出解析同路，
    # 类型 / 枚举 / 长度 / 日期全查——str(…) 判空会把整数文本误判 PASS）。
    try:
        PlanConfirmPayload.model_validate_json(json.dumps(plan, ensure_ascii=False))
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        return False, f"载荷不符合生产 Schema（{loc}: {first['msg']}）"
    phases = plan["phases"]
    # 评测特有约束：阶段 2~5（生成 prompt 契约，checklist §2 结构完整率；
    # Schema 只保证 1~8 非空，不覆盖本项）。
    if not 2 <= len(phases) <= 5:
        return False, f"阶段数 {len(phases)} 不在 2~5"
    items: list[dict[str, Any]] = [item for phase in phases for item in phase["items"]]

    daily = goal.get("daily_minutes")
    daily = daily if isinstance(daily, int) and daily > 0 else DEFAULT_DAILY_MINUTES
    deadline_raw = goal.get("target_date")
    try:
        deadline = (
            date.fromisoformat(str(deadline_raw))
            if isinstance(deadline_raw, str) and deadline_raw
            else None
        )
        claimed = [date.fromisoformat(str(item["scheduled_date"])) for item in items]
    except ValueError as exc:
        return False, f"日期不可解析：{exc}"

    constraints = ScheduleConstraints(start_date=claimed[0], deadline=deadline, daily_minutes=daily)
    try:
        expected = pack_schedule([item["estimated_minutes"] for item in items], constraints)
    except ScheduleInfeasible as exc:
        return False, f"总量铺不开（{exc}）——草案不应出现"
    if expected != claimed:
        first_diff = next(
            (i for i, (a, b) in enumerate(zip(expected, claimed, strict=True)) if a != b),
            len(expected),
        )
        return False, (
            f"第 {first_diff + 1} 项排期不符：期望 {expected[first_diff]}，"
            f"实际 {claimed[first_diff]}"
        )
    if deadline is not None and claimed[-1] > deadline:
        return False, f"排期超出期限 {deadline.isoformat()}"
    return True, f"排期逐位一致（{len(items)} 项，预算 {daily} 分钟/日）"


def main() -> int:
    files = collect_cases(sys.argv[1:])
    passed = 0
    for path in files:
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"[FAIL] {path.name}: JSON 解析失败（{exc}）")
            continue
        ok, reason = score(case if isinstance(case, dict) else {})
        passed += int(ok)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {path.name}: {reason}")
    total = len(files)
    rate = passed / total
    print(f"排期合规与结构完整率：{passed}/{total} = {rate:.0%}（门禁 100%）")
    return EXIT_PASS if passed == total else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
