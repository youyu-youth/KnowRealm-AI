"""LibraryRetrievalService：资料库 V1 唯一检索深模块（工单 04，ADR-0024）。

管线顺序冻结（contract §4）：作用域与软删过滤 → 查询规范化（jieba 索引/查询
同源）→ Segment FTS 与 CONFIRMED Concept 扩展并行召回 → 去重与确定性排序 →
回业务表取逐字原文与相邻小窗口 → 定位信息（locator）组装。三类结果中仅
evidence_hits 可引用；分数只用于排序，不出现在结果结构里。

五档 scope 隔离：RECORD 强制 record_id；LIBRARY_ITEM = 该资料直挂分片 + 其
关联 Record；COURSE = 本课程资料与记录（不含未归类）；ALL = 全部含未归类。
ARCHIVED / 软删来源不以资料身份召回（07 硬门禁）。LIKE 兜底不进入通用管线——
仅 RECORD / LIBRARY_ITEM 对范围内无分片记录按记录级路径继承（contract §4：
transcript 恒为事实源，B2 迁移期语义收编）；COURSE 档例外仅共享引用覆盖的
无分片记录（工单 05：被引用资料的 Record 内容须进入课程问答与检索——
纯文本资料无分片，FTS 路径永不命中）。
"""

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.capture.schemas import CaptureType
from app.modules.course_brain.schemas import BrainSearchConceptOut
from app.modules.course_brain.service import CourseBrainService
from app.modules.library.models import LibraryItem
from app.modules.library.schemas import ChatScope
from app.modules.record.models import Record
from app.modules.search.tokenizer import escape_like, match_expression, tokenize

# 工单 01 冻结的检索常量（contract §3；评测基线与 agent 工具复用同值）。
SEARCH_LIBRARY_LIMIT = 8
CONCEPT_MATCH_LIMIT = 4
ASSET_MATCH_LIMIT = 8
EXPANSION_PER_TERM_LIMIT = 8
CONTEXT_WINDOW_MAX_CHARS = 400

# ---------------------------------------------------------------------------
# 作用域过滤片段（内部常量拼接，不含用户输入；词法与既有 B2 过滤器同源）。
# ---------------------------------------------------------------------------

_RECORD_FILTER = "ts.record_id = :record_id"
# 文档分片的 record 路径统一要求 r.id IS NOT NULL：records 是带 deleted_at 过滤的
# LEFT JOIN，软删记录命中时 r 为 NULL，缺此条件会把软删记录的分片当作
# 「未归类」泄漏进 RECORD/ALL 范围（source_title 同步变 NULL）。
_RECORD_FILTER_DOC = "ds.record_id = :record_id AND r.id IS NOT NULL"
_ITEM_RECORD_FILTER = (
    "ts.record_id IN (SELECT lir.record_id FROM library_item_records lir "
    "WHERE lir.library_item_id = :library_item_id)"
)
_ITEM_RECORD_FILTER_DOC = (
    "ds.record_id IN (SELECT lir.record_id FROM library_item_records lir "
    "JOIN records lr ON lr.id = lir.record_id AND lr.deleted_at IS NULL "
    "WHERE lir.library_item_id = :library_item_id) AND r.id IS NOT NULL"
)
# 共享引用覆盖（工单 05）：被引用资料的 Record（经条目关联）与条目本身纳入
# COURSE 检索范围；条目存活过滤（软删即失效、恢复即复活，查询期派生）内联
# 于此，record 存活由消费 SQL 的 JOIN r.deleted_at IS NULL 行级保证。
_SHARED_RECORD_IDS_SQL = (
    "SELECT lir.record_id FROM library_item_records lir "
    "JOIN course_shared_refs csr ON csr.library_item_id = lir.library_item_id "
    "JOIN library_items li ON li.id = lir.library_item_id "
    "AND li.status = 'ACTIVE' AND li.deleted_at IS NULL "
    "WHERE csr.course_id = :course_id"
)
_SHARED_ITEM_IDS_SQL = (
    "SELECT csr.library_item_id FROM course_shared_refs csr "
    "JOIN library_items li ON li.id = csr.library_item_id "
    "AND li.status = 'ACTIVE' AND li.deleted_at IS NULL "
    "WHERE csr.course_id = :course_id"
)
_COURSE_FILTER = f"(r.course_id = :course_id OR r.id IN ({_SHARED_RECORD_IDS_SQL}))"
_COURSE_FILTER_DOC = (
    f"ds.record_id IS NOT NULL AND r.id IS NOT NULL "
    f"AND (r.course_id = :course_id OR r.id IN ({_SHARED_RECORD_IDS_SQL}))"
)
# ALL：未归类记录直过，已归类须课程未软删（口径对齐 B2 记录清单过滤器）。
_ALL_RECORD_ALIVE = (
    "(r.id IS NOT NULL AND (r.course_id IS NULL OR EXISTS ("
    "SELECT 1 FROM courses c WHERE c.id = r.course_id AND c.deleted_at IS NULL)))"
)
_ALL_FILTER = _ALL_RECORD_ALIVE
_ALL_FILTER_DOC = f"ds.record_id IS NOT NULL AND {_ALL_RECORD_ALIVE}"
# 资料直挂分片（03 网页剪藏起写入）：条目须 ACTIVE 且未软删；ALL 额外要求
# 课程存活或未归类（LIBRARY_ITEM 由条目身份保证、COURSE 由条目课程边界保证）。
_ITEM_DIRECT_LIB = "ds.library_item_id = :library_item_id"
_ITEM_DIRECT_COURSE = (
    "(ds.library_item_id IN (SELECT li.id FROM library_items li "
    "WHERE li.course_id = :course_id AND li.status = 'ACTIVE' "
    "AND li.deleted_at IS NULL) "
    f"OR ds.library_item_id IN ({_SHARED_ITEM_IDS_SQL}))"
)
_ITEM_DIRECT_ALL = (
    "ds.library_item_id IN (SELECT li.id FROM library_items li "
    "WHERE li.status = 'ACTIVE' AND li.deleted_at IS NULL "
    "AND (li.course_id IS NULL OR EXISTS (SELECT 1 FROM courses c2 "
    "WHERE c2.id = li.course_id AND c2.deleted_at IS NULL)))"
)


def _transcript_sql(record_filter: str) -> TextClause:
    return text(
        "SELECT ts.id AS segment_id, ts.record_id, r.title AS source_title, "
        "ts.content, ts.sequence_no, ts.record_start_ms, ts.record_end_ms, "
        "bm25(segment_search_index) AS score "
        "FROM segment_search_index "
        "JOIN transcript_segments ts ON ts.id = segment_search_index.entity_id "
        "JOIN transcripts t ON t.id = ts.transcript_id AND t.deleted_at IS NULL "
        "JOIN records r ON r.id = ts.record_id AND r.deleted_at IS NULL "
        "WHERE segment_search_index MATCH :match "
        "AND segment_search_index.entity_type = 'transcript_segment' "
        f"AND {record_filter} "
        "ORDER BY score, ts.id LIMIT :limit"
    )


def _document_sql(record_filter: str, item_filter: str | None = None) -> TextClause:
    """文档分片双路径：record 挂靠（记录存活 + 范围过滤）或资料直挂（条目存活 + 范围过滤）。

    RECORD 范围只走 record 路径（边界=该记录，不含资料直挂分片）。
    """
    item_clause = f" OR ({item_filter})" if item_filter is not None else ""
    return text(
        "SELECT ds.id AS segment_id, ds.record_id, "
        "COALESCE(r.title, li.title) AS source_title, ds.library_item_id, "
        "li.source_type AS item_source_type, ds.content, ds.sequence_no, "
        "ds.page_no, bm25(segment_search_index) AS score "
        "FROM segment_search_index "
        "JOIN document_segments ds ON ds.id = segment_search_index.entity_id "
        "LEFT JOIN records r ON r.id = ds.record_id AND r.deleted_at IS NULL "
        "LEFT JOIN library_items li ON li.id = ds.library_item_id "
        "AND li.status = 'ACTIVE' AND li.deleted_at IS NULL "
        "WHERE segment_search_index MATCH :match "
        "AND segment_search_index.entity_type = 'document_segment' "
        f"AND (({record_filter}){item_clause}) "
        "ORDER BY score, ds.id LIMIT :limit"
    )


_SCOPE_SEGMENT_SQL: dict[ChatScope, tuple[TextClause, TextClause]] = {
    ChatScope.RECORD: (_transcript_sql(_RECORD_FILTER), _document_sql(_RECORD_FILTER_DOC)),
    ChatScope.LIBRARY_ITEM: (
        _transcript_sql(_ITEM_RECORD_FILTER),
        _document_sql(_ITEM_RECORD_FILTER_DOC, _ITEM_DIRECT_LIB),
    ),
    ChatScope.COURSE: (
        _transcript_sql(_COURSE_FILTER),
        _document_sql(_COURSE_FILTER_DOC, _ITEM_DIRECT_COURSE),
    ),
    ChatScope.ALL: (_transcript_sql(_ALL_FILTER), _document_sql(_ALL_FILTER_DOC, _ITEM_DIRECT_ALL)),
}

# 概念扩展词专用（COURSE/ALL：概念只在其归属课程内扩展，历史语义照搬）。
_EXPANSION_COURSE_SQL = (
    _transcript_sql(_COURSE_FILTER),
    _document_sql(_COURSE_FILTER_DOC, _ITEM_DIRECT_COURSE),
)

# 无分片记录的 transcript 子串兜底（RECORD / LIBRARY_ITEM 的记录级继承路径）。
# COURSE 档（工单 05）仅共享引用覆盖的记录兜底：本课程自己的无分片记录维持
# contract §4 不兜底口径——spec 承诺的是「被引用资料的 Record 内容进入课程
# 问答与检索」，不扩大到课程自有记录。
_SCOPE_FALLBACK_SQL: dict[ChatScope, TextClause] = {
    ChatScope.RECORD: text(
        "SELECT r.id AS record_id, r.title AS record_title, t.content "
        "FROM transcripts t JOIN records r ON r.id = t.record_id "
        "WHERE t.record_id = :record_id AND t.deleted_at IS NULL "
        "AND r.deleted_at IS NULL"
    ),
    ChatScope.LIBRARY_ITEM: text(
        "SELECT r.id AS record_id, r.title AS record_title, t.content "
        "FROM transcripts t "
        "JOIN records r ON r.id = t.record_id AND r.deleted_at IS NULL "
        "JOIN library_item_records lir ON lir.record_id = r.id "
        "WHERE lir.library_item_id = :library_item_id AND t.deleted_at IS NULL"
    ),
    ChatScope.COURSE: text(
        "SELECT r.id AS record_id, r.title AS record_title, t.content "
        "FROM transcripts t "
        "JOIN records r ON r.id = t.record_id AND r.deleted_at IS NULL "
        f"WHERE r.id IN ({_SHARED_RECORD_IDS_SQL}) AND t.deleted_at IS NULL"
    ),
}

# 范围内「已有分片」的记录集合（兜底只对无分片记录生效，spec 语义）。
_RECORDS_WITH_SEGMENTS_SQL = text(
    "SELECT DISTINCT record_id FROM transcript_segments WHERE record_id IN :ids "
    "UNION SELECT DISTINCT record_id FROM document_segments WHERE record_id IN :ids"
).bindparams(bindparam("ids", expanding=True))

# 记录 → 代表性资料条目（按关联 sequence_no/创建序取首项，确定性）：
# evidence 的资料身份与来源类型用。
_RECORD_ITEMS_SQL = text(
    "SELECT lir.record_id AS rid, li.id, li.source_type "
    "FROM library_item_records lir "
    "JOIN library_items li ON li.id = lir.library_item_id "
    "AND li.status = 'ACTIVE' AND li.deleted_at IS NULL "
    "WHERE lir.record_id IN :ids "
    "ORDER BY lir.record_id, lir.sequence_no, lir.created_at, li.id"
).bindparams(bindparam("ids", expanding=True))

# 相邻窗口取数：同一宿主（记录或资料直挂）sequence_no ±1 的分片内容。
_NEIGHBOR_TRANSCRIPTS_SQL = text(
    "SELECT sequence_no, content FROM transcript_segments "
    "WHERE record_id = :record_id AND sequence_no IN :seqs"
).bindparams(bindparam("seqs", expanding=True))
_NEIGHBOR_DOCUMENTS_BY_RECORD_SQL = text(
    "SELECT sequence_no, content FROM document_segments "
    "WHERE record_id = :record_id AND sequence_no IN :seqs"
).bindparams(bindparam("seqs", expanding=True))
_NEIGHBOR_DOCUMENTS_BY_ITEM_SQL = text(
    "SELECT sequence_no, content FROM document_segments "
    "WHERE library_item_id = :library_item_id AND record_id IS NULL "
    "AND sequence_no IN :seqs"
).bindparams(bindparam("seqs", expanding=True))

# 记录 capture_type → 来源类型（记录无资料条目时的确定性回退映射）。
_SOURCE_TYPE_BY_CAPTURE: dict[str, str] = {
    CaptureType.RECORDING.value: "AUDIO",
    CaptureType.AUDIO_IMPORT.value: "AUDIO",
    CaptureType.MULTI_SOURCE.value: "DOCUMENT",
    CaptureType.DOCUMENT_IMPORT.value: "DOCUMENT",
    CaptureType.PASTE.value: "TEXT",
    CaptureType.QUICK_NOTE.value: "TEXT",
    CaptureType.CLIP.value: "WEB",
}

_RETRIEVAL_SCOPES = (
    ChatScope.RECORD,
    ChatScope.LIBRARY_ITEM,
    ChatScope.COURSE,
    ChatScope.ALL,
)


@dataclass(frozen=True)
class RetrievalScope:
    """检索范围（运行期由会话派生）：RECORD / LIBRARY_ITEM / COURSE / ALL 之一。"""

    scope: ChatScope
    record_id: str | None = None
    library_item_id: str | None = None
    course_id: str | None = None


@dataclass(frozen=True)
class EvidenceHit:
    """唯一可引用命中：quote 必为业务表（分片/转写）逐字原文。"""

    record_id: str | None
    library_item_id: str | None
    source_title: str
    quote: str
    context_window: str
    segment_id: str
    locator: dict[str, object] = field(default_factory=dict[str, object])
    source_type: str = "TEXT"
    channel: str = "fts"
    # 共享来源标志（工单 05）：命中宿主不属于 scope 课程、经共享引用覆盖时置
    # True（引用行标注「共享来源」）；仅 COURSE 档判定。
    shared_source: bool = False


@dataclass(frozen=True)
class AssetMatch:
    """标题导航命中：不可作为原文引用，仅帮助模型列举范围内对象。"""

    type: str  # LIBRARY_ITEM | RECORD
    id: str
    title: str


@dataclass(frozen=True)
class ConceptHint:
    """CONFIRMED 概念扩展提示：描述只是说明文字，不得当作原文引用。"""

    concept_id: str
    canonical_name: str
    description: str
    course_id: str


@dataclass(frozen=True)
class RetrievalResult:
    evidence_hits: list[EvidenceHit] = field(default_factory=list[EvidenceHit])
    asset_matches: list[AssetMatch] = field(default_factory=list[AssetMatch])
    concept_hints: list[ConceptHint] = field(default_factory=list[ConceptHint])


def _format_timestamp(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _format_time_range(start_ms: int | None, end_ms: int | None) -> str | None:
    start = _format_timestamp(start_ms) if start_ms is not None else None
    end = _format_timestamp(end_ms) if end_ms is not None else None
    if start is None:
        return end
    if end is None or end == start:
        return start
    return f"{start}-{end}"


def _substring_window(line: str, needle: str) -> str:
    """无分片兜底命中的逐字窗口：单行超长时以命中词为中心截取。"""
    if len(line) <= CONTEXT_WINDOW_MAX_CHARS:
        return line
    index = line.find(needle)
    start = max(0, index - (CONTEXT_WINDOW_MAX_CHARS - len(needle)) // 2)
    return line[start : start + CONTEXT_WINDOW_MAX_CHARS]


def _bind_params(scope: RetrievalScope) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if scope.scope == ChatScope.RECORD:
        params["record_id"] = scope.record_id
    elif scope.scope == ChatScope.LIBRARY_ITEM:
        params["library_item_id"] = scope.library_item_id
    elif scope.scope == ChatScope.COURSE:
        params["course_id"] = scope.course_id
    return params


@dataclass(frozen=True)
class _SegmentRecall:
    """一次命中的内部承载：行数据 + 实体类型 + 召回通道。

    row 为 SQL 行（属性访问）或 _FallbackRow（无分片兜底命中）。
    """

    row: Any
    entity: str  # transcript | document
    channel: str  # fts | concept_expansion | transcript_fallback


@dataclass(frozen=True)
class _FallbackRow:
    """无分片兜底命中的行形状（与分片 FTS 行列名对齐）。"""

    segment_id: str
    record_id: str
    library_item_id: str | None = None
    source_title: str = ""
    content: str = ""
    sequence_no: int | None = None
    record_start_ms: int | None = None
    record_end_ms: int | None = None
    page_no: int | None = None
    item_source_type: str | None = None


class LibraryRetrievalService:
    """检索唯一深模块：`search_library` 工具与评测/后续业务模块的共用入口。"""

    @staticmethod
    async def search(
        session: AsyncSession,
        scope: RetrievalScope,
        query: str,
        limit: int = SEARCH_LIBRARY_LIMIT,
    ) -> RetrievalResult:
        """五档 scope 检索：FTS + 概念扩展并行召回 → 去重排序 → 逐字原文 + 相邻窗口。"""
        if scope.scope not in _RETRIEVAL_SCOPES:
            return RetrievalResult()
        needle = query.strip()
        if not needle or not await LibraryRetrievalService._scope_alive(session, scope):
            return RetrievalResult()
        concepts = await CourseBrainService.match_concepts(session, scope.course_id, needle)
        recalled = await LibraryRetrievalService._recall_segments(
            session, scope, needle, concepts, limit
        )
        if not recalled:
            recalled = await LibraryRetrievalService._fallback_recalls(
                session, scope, needle, limit
            )
        return RetrievalResult(
            evidence_hits=await LibraryRetrievalService._compose_evidence(
                session,
                recalled,
                limit,
                course_id=scope.course_id if scope.scope == ChatScope.COURSE else None,
            ),
            asset_matches=await LibraryRetrievalService._asset_matches(session, scope, needle),
            concept_hints=[
                ConceptHint(
                    concept_id=concept.concept_id,
                    canonical_name=concept.canonical_name,
                    description=concept.description,
                    course_id=concept.course_id,
                )
                for concept in concepts[:CONCEPT_MATCH_LIMIT]
            ],
        )

    @staticmethod
    async def _scope_alive(session: AsyncSession, scope: RetrievalScope) -> bool:
        """RECORD / LIBRARY_ITEM 目标存活校验（COURSE/ALL 由 SQL 过滤保证）。

        会话层（accept / _session_context）已先行拦截失效态；此处兜底保证服务
        直调（测试与未来消费者）同样不越界：软删或 ARCHIVED 一律零命中。
        """
        if scope.scope == ChatScope.RECORD:
            record = await session.get(Record, scope.record_id or "")
            return record is not None and record.deleted_at is None
        if scope.scope == ChatScope.LIBRARY_ITEM:
            item = await session.get(LibraryItem, scope.library_item_id or "")
            return item is not None and item.deleted_at is None and item.status == "ACTIVE"
        return True

    @staticmethod
    async def _recall_segments(
        session: AsyncSession,
        scope: RetrievalScope,
        needle: str,
        concepts: list[BrainSearchConceptOut],
        limit: int,
    ) -> list[_SegmentRecall]:
        """FTS 召回：原查询 + 各命中概念名并跑；去重键 =（宿主身份, content）。

        确定性排序 = 召回词序（原查询优先）→ BM25 → 分片 id；概念扩展词在
        COURSE/ALL 只在其归属课程内跑（历史语义），RECORD/LIBRARY_ITEM 的边界
        即记录集，概念名仅作为改写查询词。
        """
        transcript_sql, document_sql = _SCOPE_SEGMENT_SQL[scope.scope]
        base_params = _bind_params(scope)
        terms: list[tuple[str, str, str | None]] = [(needle, "fts", None)]
        if scope.scope in (ChatScope.COURSE, ChatScope.ALL):
            terms.extend(
                (concept.canonical_name, "concept_expansion", concept.course_id)
                for concept in concepts
            )
        else:
            terms.extend(
                (concept.canonical_name, "concept_expansion", None) for concept in concepts
            )
        seen: set[tuple[str, str]] = set()
        merged: list[_SegmentRecall] = []
        for term, channel, term_course in terms:
            match = match_expression(term)
            if match is None:
                continue
            # 原查询满额（与 evidence 上限同值）；概念扩展词单次命中受冻结常量约束。
            per_term_limit = limit if channel == "fts" else min(limit, EXPANSION_PER_TERM_LIMIT)
            params: dict[str, Any] = {**base_params, "match": match, "limit": per_term_limit}
            term_transcript, term_document = transcript_sql, document_sql
            if term_course is not None:
                # 概念扩展按归属课程收窄（资料直挂路径按条目课程边界同步收窄）。
                params["course_id"] = term_course
                term_transcript, term_document = _EXPANSION_COURSE_SQL
            for sql, entity in (
                (term_transcript, "transcript"),
                (term_document, "document"),
            ):
                for row in (await session.execute(sql, params)).all():
                    owner = (
                        f"record:{row.record_id}"
                        if row.record_id is not None
                        else f"item:{row.library_item_id}"
                    )
                    key = (owner, cast(str, row.content))
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(_SegmentRecall(row=row, entity=entity, channel=channel))
                    if len(merged) >= limit:
                        return merged
        return merged

    @staticmethod
    async def _fallback_recalls(
        session: AsyncSession, scope: RetrievalScope, needle: str, limit: int
    ) -> list[_SegmentRecall]:
        """无分片记录兜底：FTS 全零命中时对范围内无分片记录做 transcript 子串检索。

        范围内任一记录已有分片即不做兜底（有分片索引的记录 FTS 无命中就如实
        返回，spec：兜底仅限无分片记录——粘贴/速记，transcript 恒为事实源）。
        兜底命中无业务分片，segment_id 以 transcript 标记（仅工具载荷展示用）。
        """
        fallback_sql = _SCOPE_FALLBACK_SQL.get(scope.scope)
        if fallback_sql is None:
            return []
        rows = (await session.execute(fallback_sql, _bind_params(scope))).all()
        if not rows:
            return []
        record_ids = [cast(str, row.record_id) for row in rows]
        with_segments = {
            cast(str, row[0])
            for row in (
                await session.execute(_RECORDS_WITH_SEGMENTS_SQL, {"ids": record_ids})
            ).all()
        }
        segmentless = [
            (cast(str, row.record_id), cast(str, row.record_title), cast(str, row.content))
            for row in rows
            if cast(str, row.record_id) not in with_segments
        ]
        recalls: list[_SegmentRecall] = []
        for record_id, record_title, content in segmentless:
            if len(recalls) >= limit:
                break
            index = content.find(needle)
            if index < 0:
                continue
            line_start = content.rfind("\n", 0, index) + 1
            line_end = content.find("\n", index)
            line_end = len(content) if line_end < 0 else line_end
            window = _substring_window(content[line_start:line_end], needle)
            recalls.append(
                _SegmentRecall(
                    row=_FallbackRow(
                        segment_id=f"transcript:{record_id}",
                        record_id=record_id,
                        source_title=record_title,
                        content=window,
                    ),
                    entity="transcript",
                    channel="transcript_fallback",
                )
            )
        return recalls

    @staticmethod
    async def _compose_evidence(
        session: AsyncSession,
        recalls: list[_SegmentRecall],
        limit: int,
        course_id: str | None = None,
    ) -> list[EvidenceHit]:
        """召回行 → 逐字 evidence：定位字段、来源类型、代表资料身份与相邻窗口。

        course_id 非 None（COURSE 档，工单 05）时判定共享来源：命中宿主的归属
        课程 ≠ scope 课程（含未归类）＝共享命中，shared_source 置 True。
        """
        record_ids = sorted(
            {
                cast(str, recall.row.record_id)
                for recall in recalls
                if getattr(recall.row, "record_id", None) is not None
            }
        )
        item_by_record: dict[str, tuple[str, str]] = {}
        capture_types = await LibraryRetrievalService._capture_types(session, record_ids)
        if record_ids:
            for link in (await session.execute(_RECORD_ITEMS_SQL, {"ids": record_ids})).all():
                item_by_record.setdefault(
                    cast(str, link.rid), (cast(str, link.id), cast(str, link.source_type))
                )
        # 命中宿主的课程归属映射（共享判定用）：record 宿主 + 条目直挂宿主。
        record_course: dict[str, str | None] = {}
        item_course: dict[str, str | None] = {}
        if course_id is not None:
            if record_ids:
                rows = await session.execute(
                    text("SELECT id, course_id FROM records WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": record_ids},
                )
                record_course = {
                    cast(str, row[0]): cast("str | None", row[1]) for row in rows.all()
                }
            host_item_ids = sorted(
                {
                    cast(str, recall.row.library_item_id)
                    for recall in recalls
                    if getattr(recall.row, "library_item_id", None) is not None
                }
            )
            if host_item_ids:
                rows = await session.execute(
                    text("SELECT id, course_id FROM library_items WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": host_item_ids},
                )
                item_course = {
                    cast(str, row[0]): cast("str | None", row[1]) for row in rows.all()
                }
        evidence: list[EvidenceHit] = []
        for recall in recalls[:limit]:
            row = recall.row
            record_id = cast("str | None", getattr(row, "record_id", None))
            library_item_id = cast("str | None", getattr(row, "library_item_id", None))
            representative = item_by_record.get(record_id) if record_id is not None else None
            if library_item_id is not None:
                source_type = cast(str, getattr(row, "item_source_type", None) or "TEXT")
            elif representative is not None:
                source_type = representative[1]
            else:
                source_type = _SOURCE_TYPE_BY_CAPTURE.get(
                    capture_types.get(record_id or "", ""), "TEXT"
                )
            # 共享判定（工单 05）：按命中宿主归属（record 宿主优先，直挂分片
            # 无 record 时按条目归属）；代表条目只是身份回填不参与判定。
            shared_source = False
            if course_id is not None:
                if record_id is not None:
                    shared_source = record_course.get(record_id) != course_id
                elif library_item_id is not None:
                    shared_source = item_course.get(library_item_id) != course_id
            locator: dict[str, object] = {}
            time_range = _format_time_range(
                cast("int | None", getattr(row, "record_start_ms", None)),
                cast("int | None", getattr(row, "record_end_ms", None)),
            )
            if time_range is not None:
                locator["time"] = time_range
            page_no = cast("int | None", getattr(row, "page_no", None))
            if page_no is not None:
                locator["page"] = page_no
            quote = cast(str, row.content)
            evidence.append(
                EvidenceHit(
                    record_id=record_id,
                    library_item_id=library_item_id
                    or (representative[0] if representative is not None else None),
                    source_title=cast(str, row.source_title),
                    quote=quote,
                    context_window=await LibraryRetrievalService._context_window(
                        session, recall, quote
                    ),
                    segment_id=cast(str, row.segment_id),
                    locator=locator,
                    source_type=source_type,
                    channel=recall.channel,
                    shared_source=shared_source,
                )
            )
        return evidence

    @staticmethod
    async def _capture_types(session: AsyncSession, record_ids: list[str]) -> dict[str, str]:
        if not record_ids:
            return {}
        rows = await session.execute(
            text("SELECT id, capture_type FROM records WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": record_ids},
        )
        return {cast(str, row[0]): cast(str, row[1]) for row in rows.all()}

    @staticmethod
    async def _context_window(session: AsyncSession, recall: _SegmentRecall, quote: str) -> str:
        """相邻小窗口：同宿主 sequence_no ±1 的分片内容拼接，≤400 字符。

        兜底命中的窗口即命中行本身（构造时已是受限窗口）；窗口只是相邻上下文
        提示，不作为引用依据（引用逐字校验只看 quote）。
        """
        row = recall.row
        sequence_no = cast("int | None", getattr(row, "sequence_no", None))
        if recall.channel == "transcript_fallback" or sequence_no is None:
            return quote[:CONTEXT_WINDOW_MAX_CHARS]
        seqs = [sequence_no - 1, sequence_no + 1]
        record_id = getattr(row, "record_id", None)
        library_item_id = getattr(row, "library_item_id", None)
        if record_id is not None:
            neighbors_sql = (
                _NEIGHBOR_TRANSCRIPTS_SQL
                if recall.entity == "transcript"
                else _NEIGHBOR_DOCUMENTS_BY_RECORD_SQL
            )
            neighbors = (
                await session.execute(neighbors_sql, {"record_id": record_id, "seqs": seqs})
            ).all()
        elif library_item_id is not None:
            neighbors = (
                await session.execute(
                    _NEIGHBOR_DOCUMENTS_BY_ITEM_SQL,
                    {"library_item_id": library_item_id, "seqs": seqs},
                )
            ).all()
        else:
            neighbors = []
        by_seq: dict[int, str] = {}
        for item in cast("list[Any]", neighbors):
            by_seq[cast(int, item.sequence_no)] = cast(str, item.content)
        window = " ".join(
            part
            for part in (by_seq.get(sequence_no - 1), quote, by_seq.get(sequence_no + 1))
            if part
        )
        return window[:CONTEXT_WINDOW_MAX_CHARS]

    @staticmethod
    async def _asset_matches(
        session: AsyncSession, scope: RetrievalScope, needle: str
    ) -> list[AssetMatch]:
        """标题导航命中：查询 token（≥2 字符）任一出现在标题即算，条目 + 记录
        合并按 updated_at 降序取前 8；范围内过滤与 evidence 同口径。"""
        tokens = [token for token in tokenize(needle).split() if len(token) >= 2]
        if not tokens:
            return []
        conditions = " OR ".join(
            f"title LIKE :needle{index} ESCAPE '\\'" for index in range(len(tokens))
        )
        like_params = {
            f"needle{index}": f"%{escape_like(token)}%" for index, token in enumerate(tokens)
        }
        params = {**_bind_params(scope), **like_params, "limit": ASSET_MATCH_LIMIT}
        item_sql = LibraryRetrievalService._asset_items_sql(scope.scope, conditions)
        record_sql = LibraryRetrievalService._asset_records_sql(scope.scope, conditions)
        item_rows = (await session.execute(item_sql, params)).all()
        record_rows = (await session.execute(record_sql, params)).all()
        item_ids = {cast(str, row.id) for row in item_rows}
        candidates = [
            *((row.updated_at, cast(str, row.id), cast(str, row.title)) for row in item_rows),
            *(
                (row.updated_at, cast(str, row.id), cast(str, row.title))
                for row in record_rows
                if cast(str, row.id) not in item_ids
            ),
        ]
        candidates.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        return [
            AssetMatch(
                type="LIBRARY_ITEM" if row_id in item_ids else "RECORD",
                id=row_id,
                title=title,
            )
            for _updated, row_id, title in candidates[:ASSET_MATCH_LIMIT]
        ]

    @staticmethod
    def _asset_items_sql(scope: ChatScope, title_conditions: str) -> TextClause:
        scope_filter = {
            ChatScope.RECORD: (
                "li.id IN (SELECT lir.library_item_id FROM library_item_records lir "
                "JOIN records r ON r.id = lir.record_id AND r.deleted_at IS NULL "
                "WHERE r.id = :record_id)"
            ),
            ChatScope.LIBRARY_ITEM: "li.id = :library_item_id",
            ChatScope.COURSE: (
                f"(li.course_id = :course_id OR li.id IN ({_SHARED_ITEM_IDS_SQL}))"
            ),
            ChatScope.ALL: "TRUE",
        }[scope]
        return text(
            "SELECT li.id, li.title, li.updated_at FROM library_items li "
            f"WHERE li.deleted_at IS NULL AND li.status = 'ACTIVE' AND ({scope_filter}) "
            f"AND ({title_conditions}) "
            "ORDER BY li.updated_at DESC, li.id DESC LIMIT :limit"
        )

    @staticmethod
    def _asset_records_sql(scope: ChatScope, title_conditions: str) -> TextClause:
        scope_filter = {
            ChatScope.RECORD: "records.id = :record_id",
            ChatScope.LIBRARY_ITEM: (
                "records.id IN (SELECT lir.record_id FROM library_item_records lir "
                "WHERE lir.library_item_id = :library_item_id)"
            ),
            ChatScope.COURSE: (
                f"(records.course_id = :course_id "
                f"OR records.id IN ({_SHARED_RECORD_IDS_SQL}))"
            ),
            ChatScope.ALL: (
                "(records.course_id IS NULL OR EXISTS (SELECT 1 FROM courses c "
                "WHERE c.id = records.course_id AND c.deleted_at IS NULL))"
            ),
        }[scope]
        return text(
            "SELECT records.id, records.title, records.updated_at FROM records "
            f"WHERE records.deleted_at IS NULL AND ({scope_filter}) "
            f"AND ({title_conditions}) "
            "ORDER BY records.updated_at DESC, records.id DESC LIMIT :limit"
        )
