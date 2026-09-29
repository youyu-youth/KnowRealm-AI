"""学习计划生成黄金集「排期合规 / 结构完整」评分脚本（第三阶段工单 02）。

用法：先按 `docs/evaluation/plan-generation-checklist.md` §3 采集草案（每题
一个 .json 采集文件，形态见 plan-generation-samples.md §2），再执行：

    uv run python -m scripts.score_plan_generation <采集文件或目录...>

对每个文件机械复算三件事（红线指标）：
1. 排期逐位等于确定性铺排（顺序 + 每日预算 + 首日锚定，与
   learning_plan.scheduling.pack_schedule 同源）；
2. 全部排期不超目标期限（无期限跳过该项）；
3. 结构完整：阶段 ≥1、每项 action_type 合法且 content / reason /
   estimated_minutes 非空。

输出逐文件判定与整体通过率（门禁 100%）；资料贴合度与理由可解释性按
checklist §2 rubric 人工评，本脚本不覆盖。
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from app.modules.learning_plan.scheduling import (
    DEFAULT_DAILY_MINUTES,
    ScheduleConstraints,
    ScheduleInfeasible,
    pack_schedule,
)

EXIT_PASS = 0
EXIT_FAIL = 1

_ACTION_TYPES = {"STUDY_RECORD", "PRACTICE_QUIZ", "REVIEW_CONCEPT", "CUSTOM"}


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
    phases = plan.get("phases")
    if not isinstance(phases, list) or not phases:
        return False, "没有阶段（phases 为空）"

    items: list[dict[str, Any]] = []
    for phase in phases:
        if not isinstance(phase, dict) or not str(phase.get("title") or "").strip():
            return False, "存在无标题阶段"
        phase_items = phase.get("items")
        if not isinstance(phase_items, list) or not phase_items:
            return False, "存在空阶段（无计划项）"
        for item in phase_items:
            if not isinstance(item, dict):
                return False, "计划项形状非法"
            if item.get("action_type") not in _ACTION_TYPES:
                return False, f"action_type 非法：{item.get('action_type')}"
            if not str(item.get("content") or "").strip():
                return False, "计划项 content 为空"
            if not str(item.get("reason") or "").strip():
                return False, "计划项 reason 为空（理由缺失）"
            minutes = item.get("estimated_minutes")
            if not isinstance(minutes, int) or minutes < 1:
                return False, "estimated_minutes 非法"
            if not str(item.get("scheduled_date") or "").strip():
                return False, "计划项 scheduled_date 为空"
            items.append(item)
    if not items:
        return False, "草案没有计划项"

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
