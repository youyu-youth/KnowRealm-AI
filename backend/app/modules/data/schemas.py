from pydantic import BaseModel, Field


class DataDirectoryExportRequest(BaseModel):
    """全量导出请求；include_secrets=true 时 providers.json 明文随包。"""

    include_secrets: bool = Field(default=False, description="是否包含 config/providers.json")


class DataDirectoryExportOut(BaseModel):
    file_name: str


class DataDirectoryLibraryStateOut(BaseModel):
    """空库判定（无课程+无记录+无档案）：空库时设置页可见导入兜底入口。"""

    empty_library: bool
