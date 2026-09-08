"""带稳定错误码的 HTTP 错误（γ′ 附加字段契约，见 ADR-0017）。

错误响应统一序列化为 {detail, code, params?}：detail 中文原文保留，
前端按 code 翻译、未命中回显 detail。生产代码禁止 raise 裸
HTTPException，必须走本子类（防线测试 tests/test_error_code_guard.py）。
"""

from fastapi import HTTPException


class CodedHTTPException(HTTPException):
    """必须携带稳定错误码的 HTTP 错误；params 为可选的翻译插值参数。"""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        detail: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.params = params
