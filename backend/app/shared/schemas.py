from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str = Field(description="可直接展示的错误说明")
