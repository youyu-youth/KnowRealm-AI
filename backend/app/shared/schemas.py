from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str = Field(description="可直接展示的错误说明")
    code: str = Field(description="稳定错误码，供前端按码翻译")
    params: dict[str, str] | None = Field(default=None, description="错误码插值参数")
