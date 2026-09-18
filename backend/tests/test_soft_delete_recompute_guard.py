"""防线：调用 Record/Course soft_delete 的模块必须接线 Mastery 重算。

删除不产生学习事件（票 04），漏调 recompute_concepts 的删除入口不会报错，
只会留下陈旧快照——用 AST 扫描把「忘记接线」变成测试红，而非静默数据漂移。
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
SOFT_DELETE_SERVICES = {"RecordService", "CourseService"}


def _soft_delete_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "soft_delete"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in SOFT_DELETE_SERVICES
        ):
            lines.append(node.lineno)
    return lines


def _references_recompute(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr == "recompute_concepts"
        for node in ast.walk(tree)
    )


def test_soft_delete_callers_must_wire_mastery_recompute() -> None:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls = _soft_delete_lines(tree)
        if calls and not _references_recompute(tree):
            violations.append(f"{path.relative_to(APP_DIR)}:{calls} soft_delete 未接线重算")
    assert violations == []
