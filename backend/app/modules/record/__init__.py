"""记录域模块：中心聚合 Record 的服务、课程改派、转写编辑与 SSE 失效通知。

跨模块取 ``RecordInvalidationNotifier`` 一律经 ``record.events`` 叶子直引
（jobs 等平台模块依赖它，绕开包级初始化环）。
"""

from app.modules.record.classification import RecordClassificationService
from app.modules.record.service import RecordService

__all__ = [
    "RecordClassificationService",
    "RecordService",
]
