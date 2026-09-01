"""课程域模块：Course 聚合、ARCHIVED 护栏与课程墓碑清剿。"""

from app.modules.course.service import CourseService
from app.modules.course.tombstone_cleanup import DocumentCleanupService

__all__ = [
    "CourseService",
    "DocumentCleanupService",
]
