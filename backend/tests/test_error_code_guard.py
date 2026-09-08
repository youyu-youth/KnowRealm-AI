"""防线：生产代码禁止 raise 裸 HTTPException（工单 20-03）。

全部 HTTP 错误必须走 CodedHTTPException 携带稳定错误码（框架级
RequestValidationError / 未捕获异常由 main.py 统一处理器兜底通用码），
保证前端按码翻译（工单 04）的覆盖率不随迭代回退。
"""

import ast
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CODE_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")


def test_production_code_never_raises_bare_http_exception() -> None:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = getattr(target, "id", None) or getattr(target, "attr", None)
            if name == "HTTPException":
                violations.append(f"{path.relative_to(APP_DIR)}:{node.lineno} 裸 HTTPException")
                continue
            if name != "CodedHTTPException" or not isinstance(node.exc, ast.Call):
                continue
            code_kw = next((kw for kw in node.exc.keywords if kw.arg == "code"), None)
            value = getattr(code_kw, "value", None)
            if isinstance(value, ast.Constant) and not (
                isinstance(value.value, str) and CODE_NAME_RE.fullmatch(value.value)
            ):
                violations.append(f"{path.relative_to(APP_DIR)}:{node.lineno} 码名不符规范")
    assert violations == []
