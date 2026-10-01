"""共享来源引用领域模块（通用 Agent 第三阶段工单 05，spec 用户故事 20~25）。

course ↔ library_item 多对多：资料保归属被多空间复用、不重复入库。失效为
查询期派生（条目软删即失效、恢复即复活，不设失效状态字段）；条目物理删除
经 FK CASCADE 清理；归属迁移只改 library_items.course_id 不触引用表。

引用作用范围 = 检索覆盖 + 资产只读（spec「共享引用语义」）：
- 检索覆盖：shared_alive_* 谓词供问答材料与检索范围扩展（COURSE 档纳入被
  引用资料的 Record 内容与条目直挂分片）；
- 资产只读：assert_asset_generation_allowed 在生成端点 Service 层执法——
  新空间视角（request_course_id）对「不属于本空间、经共享引用进入」的记录
  拒绝生成总结 / 知识点 / 习题（SHARED_REF_ASSET_READ_ONLY），资产仍只在
  原空间；引用不授予改、删、迁移原资料的权限（引用面零写路径）。
"""

from datetime import datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import Query
from sqlalchemy import Row, Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.course.models import Course
from app.modules.course.service import CourseService
from app.modules.library.models import CourseSharedRef, LibraryItem, LibraryItemRecord
from app.modules.library.schemas import SharedRefOut
from app.modules.record.models import Record
from app.shared.errors import CodedHTTPException

# 请求方知识空间上下文（共享引用场景携带；新空间对引用资料只读）。三个资产
# 生成路由（总结 / 知识点 / 习题）与引用路由共用此契约，定义在领域模块一处
# 维护（路由层只做透传，跨模块直达具体文件）。
REQUEST_COURSE_ID = Annotated[
    UUID | None,
    Query(description="请求方知识空间上下文：携带时对共享引用资料只读（拒绝生成资产）"),
]


def shared_alive_item_ids(course_id: str) -> Select[tuple[str]]:
    """课程被引用的存活条目 id 子查询（消息材料等 ORM 查询复用）。

    存活 = 条目 ACTIVE 且未软删（失效查询期派生口径的唯一事实源）。
    """
    return (
        select(LibraryItem.id)
        .join(CourseSharedRef, CourseSharedRef.library_item_id == LibraryItem.id)
        .where(
            CourseSharedRef.course_id == course_id,
            LibraryItem.deleted_at.is_(None),
            LibraryItem.status == "ACTIVE",
        )
    )


def shared_alive_record_ids(course_id: str) -> Select[tuple[str]]:
    """被引用条目覆盖的 record id 子查询（记录未软删由消费方行级过滤保证）。"""
    return (
        select(LibraryItemRecord.record_id)
        .join(CourseSharedRef, CourseSharedRef.library_item_id == LibraryItemRecord.library_item_id)
        .join(
            LibraryItem,
            LibraryItem.id == LibraryItemRecord.library_item_id,
        )
        .where(
            CourseSharedRef.course_id == course_id,
            LibraryItem.deleted_at.is_(None),
            LibraryItem.status == "ACTIVE",
        )
    )


# 引用行展示投影（列名消歧后属性访问，list 与单行构造共用同一形状）。
_REF_ROW_COLUMNS = (
    CourseSharedRef.created_at,
    LibraryItem.title,
    LibraryItem.source_type,
    LibraryItem.course_id.label("owner_course_id"),
    Course.name.label("owner_course_name"),
)


async def _ref_row(session: AsyncSession, course_id: str, library_item_id: str) -> Row[Any] | None:
    """引用行的展示投影（条目标题 / 来源类型 / 归属空间；available 恒 True——
    调用方 add_core 刚过 validate_add 存活校验）。"""
    statement = (
        select(*_REF_ROW_COLUMNS)
        .join(LibraryItem, LibraryItem.id == CourseSharedRef.library_item_id)
        .outerjoin(Course, Course.id == LibraryItem.course_id)
        .where(
            CourseSharedRef.course_id == course_id,
            CourseSharedRef.library_item_id == library_item_id,
        )
    )
    return (await session.execute(statement)).one_or_none()


def _out(course_id: str, library_item_id: str, row: Row[Any]) -> SharedRefOut:
    return SharedRefOut(
        course_id=course_id,
        library_item_id=library_item_id,
        title=cast(str, row.title),
        source_type=cast(str, row.source_type),
        owner_course_id=cast("str | None", row.owner_course_id),
        owner_course_name=cast("str | None", row.owner_course_name),
        available=True,
        created_at=cast(datetime, row.created_at),
    )


async def validate_add(session: AsyncSession, course_id: str, item_id: str) -> None:
    """添加引用前置校验（页面与 Agent 提交期共用）：课程可见、条目存在且可引用。"""
    course = await CourseService.get(session, course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    item = await session.get(LibraryItem, item_id)
    if item is None or item.deleted_at is not None:
        raise CodedHTTPException(
            code="LIBRARY_ITEM_NOT_FOUND", status_code=404, detail="资料条目不存在或已删除"
        )
    if item.status != "ACTIVE":
        raise CodedHTTPException(
            code="LIBRARY_ITEM_NOT_FOUND", status_code=404, detail="资料条目不存在或已删除"
        )
    if item.course_id == course_id:
        raise CodedHTTPException(
            code="SHARED_REF_ITEM_OWNED",
            status_code=409,
            detail="该资料已归属本知识空间，无需引用",
        )
    existing = await session.scalar(
        select(CourseSharedRef.id).where(
            CourseSharedRef.course_id == course_id,
            CourseSharedRef.library_item_id == item_id,
        )
    )
    if existing is not None:
        raise CodedHTTPException(
            code="SHARED_REF_DUPLICATE", status_code=409, detail="该资料已被本知识空间引用"
        )


async def assert_asset_generation_allowed(
    session: AsyncSession, record: Record, request_course_id: str | None
) -> None:
    """资产只读防线（spec 用户故事 22）：新空间视角对共享资料拒绝生成资产。

    request_course_id 缺省（无空间上下文）或记录本就归属该空间 → 放行（原空间
    视角生成是合法能力）；记录不属于该空间且经共享引用覆盖（其资料条目被该
    空间引用且存活）→ SHARED_REF_ASSET_READ_ONLY；记录与该空间无共享关系
    （无关上下文）→ 放行，由生成路径自身的归属校验（COURSE_ARCHIVED 等）
    执法，不在此越权拦截。
    """
    if request_course_id is None or record.course_id == request_course_id:
        return
    # 记录经条目关联被该空间共享引用覆盖（存活谓词复用失效派生唯一口径）。
    shared = await session.scalar(
        select(LibraryItemRecord.library_item_id)
        .where(
            LibraryItemRecord.record_id == record.id,
            LibraryItemRecord.library_item_id.in_(shared_alive_item_ids(request_course_id)),
        )
        .limit(1)
    )
    if shared is not None:
        raise CodedHTTPException(
            code="SHARED_REF_ASSET_READ_ONLY",
            status_code=409,
            detail="共享来源引用只读：总结、知识点、习题等资产只能在资料原知识空间生成",
        )


async def guard_asset_generation(
    session: AsyncSession, record_id: str, request_course_id: str | None
) -> None:
    """生成端点 submit 前置包装：record 不存在交由既有 RECORD_NOT_FOUND 执法。"""
    if request_course_id is None:
        return
    record = await session.get(Record, record_id)
    if record is None:
        return
    await assert_asset_generation_allowed(session, record, request_course_id)


class SharedRefService:
    """共享引用增删查（页面路由与 Agent 操作应用器共用，薄壳零业务分支）。"""

    @staticmethod
    async def list_for_course(session: AsyncSession, course_id: str) -> list[SharedRefOut] | None:
        """课程引用清单（None = 课程不存在或已删除）；available 为派生失效位。"""
        course = await CourseService.get(session, course_id)
        if course is None:
            return None
        statement = (
            select(
                CourseSharedRef.library_item_id,
                *_REF_ROW_COLUMNS,
                LibraryItem.deleted_at,
                LibraryItem.status,
            )
            .join(LibraryItem, LibraryItem.id == CourseSharedRef.library_item_id)
            .outerjoin(Course, Course.id == LibraryItem.course_id)
            .where(CourseSharedRef.course_id == course_id)
            .order_by(CourseSharedRef.created_at, CourseSharedRef.id)
        )
        rows = (await session.execute(statement)).all()
        return [
            SharedRefOut(
                course_id=course_id,
                library_item_id=cast(str, row.library_item_id),
                title=cast(str, row.title),
                source_type=cast(str, row.source_type),
                owner_course_id=cast("str | None", row.owner_course_id),
                owner_course_name=cast("str | None", row.owner_course_name),
                available=row.deleted_at is None and cast(str, row.status) == "ACTIVE",
                created_at=cast(datetime, row.created_at),
            )
            for row in rows
        ]

    @staticmethod
    async def add_core(session: AsyncSession, course_id: str, item_id: str) -> SharedRefOut:
        """创建事务内核心：校验＋落引用行（幂等语义由 UNIQUE 兜底并发）。"""
        await validate_add(session, course_id, item_id)
        ref = CourseSharedRef(course_id=course_id, library_item_id=item_id)
        session.add(ref)
        await session.flush()
        row = await _ref_row(session, course_id, item_id)
        assert row is not None  # 同事务刚写入
        return _out(course_id, item_id, row)

    @staticmethod
    async def add(session: AsyncSession, course_id: str, item_id: str) -> SharedRefOut:
        """HTTP / Agent 创建入口（校验失败抛稳定错误码）。"""
        async with session.begin():
            return await SharedRefService.add_core(session, course_id, item_id)

    @staticmethod
    async def remove_core(session: AsyncSession, course_id: str, item_id: str) -> None:
        """删除事务内核心：引用不存在 → SHARED_REF_NOT_FOUND（原资料不动）。"""
        existing = await session.scalar(
            select(CourseSharedRef.id).where(
                CourseSharedRef.course_id == course_id,
                CourseSharedRef.library_item_id == item_id,
            )
        )
        if existing is None:
            raise CodedHTTPException(
                code="SHARED_REF_NOT_FOUND",
                status_code=404,
                detail="共享引用不存在或已删除",
            )
        await session.execute(
            delete(CourseSharedRef).where(
                CourseSharedRef.course_id == course_id,
                CourseSharedRef.library_item_id == item_id,
            )
        )

    @staticmethod
    async def remove(session: AsyncSession, course_id: str, item_id: str) -> None:
        """HTTP / Agent 删除入口。"""
        async with session.begin():
            await SharedRefService.remove_core(session, course_id, item_id)
