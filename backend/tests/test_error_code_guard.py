"""防线：生产代码禁止 raise 裸 HTTPException（工单 20-03）；错误码三方登记
（代码 ↔ docs/后端错误码清单.md ↔ 前端 zh/en 翻译，ChatTurn 票 02 回顾）。

全部 HTTP 错误必须走 CodedHTTPException 携带稳定错误码（框架级
RequestValidationError / 未捕获异常由 main.py 统一处理器兜底通用码），
保证前端按码翻译（工单 04）的覆盖率不随迭代回退；新增码漏登记清单或
翻译在此红，不再依赖评审抓住。
"""

import ast
import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
REPO_DIR = BACKEND_DIR.parent
CODE_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")


def _collect_literal_codes() -> dict[str, str]:
    """AST 收集全部 CodedHTTPException(code="字面量") 的码 → 首个出现位置。"""
    codes: dict[str, str] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "CodedHTTPException":
                continue
            code_kw = next((kw for kw in node.keywords if kw.arg == "code"), None)
            value = getattr(code_kw, "value", None)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                codes.setdefault(value.value, f"{path.relative_to(APP_DIR)}:{node.lineno}")
    return codes


def _error_code_registry() -> set[str]:
    """docs/后端错误码清单.md 表格中的反引号码全集。"""
    content = (REPO_DIR / "docs" / "后端错误码清单.md").read_text(encoding="utf-8")
    return set(re.findall(r"`([A-Z][A-Z0-9_]+)`", content))


def _translation_codes(locale: str) -> set[str]:
    """前端 i18n errors 区的码键全集。"""
    path = REPO_DIR / "apps" / "desktop" / "src" / "i18n" / "locales" / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = data.get("errors", {})
    assert isinstance(errors, dict)
    return set(errors.keys())


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


def test_coded_error_codes_registered_in_docs_and_translations() -> None:
    """CodedHTTPException 字面量码必须三方登记：错误码清单 + zh/en 翻译。"""
    codes = _collect_literal_codes()
    assert codes, "码收集为空＝AST 接缝失效，防线自身需要修复"
    registry = _error_code_registry()
    zh = _translation_codes("zh")
    en = _translation_codes("en")
    missing = {
        code: where
        for code, where in codes.items()
        if code not in registry or code not in zh or code not in en
    }
    assert missing == {}, (
        "以下错误码未完成三方登记（docs/后端错误码清单.md + zh/en 翻译）：\n"
        + "\n".join(f"  {code} @ {where}" for code, where in sorted(missing.items()))
    )
