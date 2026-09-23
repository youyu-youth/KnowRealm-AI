"""防线：执行 Record/Course 软删的调用方必须接线 Mastery 重算。

删除不产生学习事件（票 04），漏调 recompute 的删除入口不会报错，只会留下
陈旧快照——用 AST 扫描把「忘记接线」变成测试红，而非静默数据漂移。

工单 04 收拢后两类接线形态（spec 决策 15）：
- RecordService.soft_delete / soft_delete_core：返回受影响概念、由调用方
  接线（recompute_concepts 直调或 schedule_recompute_after_commit 挂钩）；
- CourseService.soft_delete / apply_soft_delete：领域函数内聚接线（重算经
  after_commit 挂钩一体编排），调用即安全、免检。

service 实现层文件（定义这些方法）豁免——它们是接线的实现处而非调用方。
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 调用方必须接线重算的裸入口（值-属性对）。
NEEDS_WIRING_CALLS = {
    ("RecordService", "soft_delete"),
    ("RecordService", "soft_delete_core"),
    ("CourseService", "soft_delete_core"),
}
# 接线形态：直接重算（record 路由）或 after_commit 挂钩（agent 应用器）。
WIRING_ATTRS = {"recompute_concepts", "schedule_recompute_after_commit"}
# 实现层方法名：定义这些方法的文件豁免（接线实现处，非调用方）。
DEFINITION_NAMES = {"soft_delete", "soft_delete_core", "apply_soft_delete"}


def _unwired_calls(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and (node.func.value.id, node.func.attr) in NEEDS_WIRING_CALLS
        ):
            lines.append(node.lineno)
    return lines


def _references_wiring(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr in WIRING_ATTRS
        for node in ast.walk(tree)
    )


def _defines_service_method(tree: ast.AST) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in DEFINITION_NAMES
        for node in ast.walk(tree)
    )


def test_soft_delete_callers_must_wire_mastery_recompute() -> None:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls = _unwired_calls(tree)
        if calls and not _references_wiring(tree) and not _defines_service_method(tree):
            violations.append(f"{path.relative_to(APP_DIR)}:{calls} soft_delete 未接线重算")
    assert violations == []
