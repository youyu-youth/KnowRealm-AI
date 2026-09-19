"""资料库 V1 黄金集检索基线评测（library-rag-v1 工单 01 冻结口径）。

评测脚本可重复执行（pytest 内嵌，临时库随 tmp_path 清理）：

    cd backend && uv run pytest tests/test_library_retrieval_eval.py --basetemp=.pytest-tmp -s

被测基线 = V1 冻结检索链「Segment FTS + CONFIRMED Concept 扩展」（即
LibraryRetrievalService 将收编的管线；不含 B2 迁移期 LIKE 兜底——服务契约
按 spec 只含 FTS/Concept/可选向量）。黄金集语料与查询、四指标阈值、
sqlite-vec 触发判据与英文结论的正本：docs/evaluation/library-rag-retrieval-baseline.md。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, TypedDict

import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.agent.tools.search_library import (
    CONCEPT_MATCH_LIMIT,
    SEARCH_LIBRARY_LIMIT,
)
from app.modules.course_brain.service import CourseBrainService, normalize_concept_name
from app.modules.search.schemas import LibrarySegmentSearchHit
from app.modules.search.segment_service import (
    ENTITY_CONCEPT,
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.transcript.sentences import content_hash

TOKEN = "test-launch-token"
NOW = "2026-09-19T08:00:00.000000Z"

COURSE_ML = "a0000000-0000-4000-8000-000000000001"
COURSE_DB = "a0000000-0000-4000-8000-000000000002"

REC_ML_AUDIO1 = "a0000000-0000-4000-8000-000000000011"
REC_ML_AUDIO2 = "a0000000-0000-4000-8000-000000000012"
REC_ML_DOC = "a0000000-0000-4000-8000-000000000013"
REC_DB_AUDIO = "a0000000-0000-4000-8000-000000000014"
REC_DB_DOC = "a0000000-0000-4000-8000-000000000015"
REC_GLOBAL_DOC = "a0000000-0000-4000-8000-000000000016"
REC_ML_DELETED = "a0000000-0000-4000-8000-000000000017"

CONCEPT_GD = "a0000000-0000-4000-8000-000000000101"
CONCEPT_BP = "a0000000-0000-4000-8000-000000000102"
CONCEPT_IDX_ML = "a0000000-0000-4000-8000-000000000103"
CONCEPT_IDX_DB = "a0000000-0000-4000-8000-000000000104"

# 工单 01 冻结的发布门禁阈值（07 收尾复跑同一黄金集断言；正本见评测文档 §5）。
RECALL_AT_8_THRESHOLD = 0.90
MRR_THRESHOLD = 0.90
NO_ANSWER_ACCURACY_THRESHOLD = 1.0
CITATION_CORRECTNESS_THRESHOLD = 1.0


class ConceptFixture(TypedDict):
    id: str
    course_id: str
    name: str
    description: str


class RecordFixture(TypedDict):
    id: str
    course_id: str | None
    capture_type: str
    title: str
    deleted: bool


class AudioSegmentFixture(TypedDict):
    id: str
    record_id: str
    kind: Literal["audio"]
    sequence_no: int
    content: str
    start_ms: int
    end_ms: int


class DocumentSegmentFixture(TypedDict):
    id: str
    record_id: str
    kind: Literal["document"]
    sequence_no: int
    content: str
    page_no: int


SegmentFixture = AudioSegmentFixture | DocumentSegmentFixture


class QueryFixture(TypedDict):
    id: str
    query: str
    scope: Literal["ML", "DB", "ALL"]
    dimension: str
    expected: tuple[str, ...]
    note: str


RECORDS: list[RecordFixture] = [
    {
        "id": REC_ML_AUDIO1,
        "course_id": COURSE_ML,
        "capture_type": "RECORDING",
        "title": "机器学习导论 第4讲 梯度与优化",
        "deleted": False,
    },
    {
        "id": REC_ML_AUDIO2,
        "course_id": COURSE_ML,
        "capture_type": "RECORDING",
        "title": "信息检索专题 倒排索引",
        "deleted": False,
    },
    {
        "id": REC_ML_DOC,
        "course_id": COURSE_ML,
        "capture_type": "DOCUMENT_IMPORT",
        "title": "Attention Is All You Need 阅读笔记",
        "deleted": False,
    },
    {
        "id": REC_DB_AUDIO,
        "course_id": COURSE_DB,
        "capture_type": "RECORDING",
        "title": "数据库系统 第7讲 索引与查询优化",
        "deleted": False,
    },
    {
        "id": REC_DB_DOC,
        "course_id": COURSE_DB,
        "capture_type": "DOCUMENT_IMPORT",
        "title": "数据库系统 事务与并发控制讲义",
        "deleted": False,
    },
    # 未归类全局资料（PASTE）：只有 ALL 范围可检索，COURSE 不含未归类。
    {
        "id": REC_GLOBAL_DOC,
        "course_id": None,
        "capture_type": "PASTE",
        "title": "费曼学习法实践笔记",
        "deleted": False,
    },
    # 软删记录：索引行存在，查询期必须被过滤（生命周期负例的唯一宿主）。
    {
        "id": REC_ML_DELETED,
        "course_id": COURSE_ML,
        "capture_type": "RECORDING",
        "title": "第3讲 支持向量机",
        "deleted": True,
    },
]

SEGMENTS: list[SegmentFixture] = [
    {
        "id": "ml-a1-s1",
        "record_id": REC_ML_AUDIO1,
        "kind": "audio",
        "sequence_no": 0,
        "content": "反向传播算法利用链式法则，把损失函数对每个参数的梯度逐层传回去。",
        "start_ms": 10000,
        "end_ms": 25000,
    },
    {
        "id": "ml-a1-s2",
        "record_id": REC_ML_AUDIO1,
        "kind": "audio",
        "sequence_no": 1,
        "content": "梯度下降通过迭代更新参数来最小化损失函数，每一步都沿着负梯度方向走。",
        "start_ms": 25000,
        "end_ms": 40000,
    },
    {
        "id": "ml-a1-s3",
        "record_id": REC_ML_AUDIO1,
        "kind": "audio",
        "sequence_no": 2,
        "content": "学习率太大会导致震荡，太小则收敛缓慢，这是调参的关键。",
        "start_ms": 40000,
        "end_ms": 55000,
    },
    {
        "id": "ml-a2-s1",
        "record_id": REC_ML_AUDIO2,
        "kind": "audio",
        "sequence_no": 0,
        "content": "搜索引擎的核心是倒排索引，它把每个词映射到包含该词的文档列表。",
        "start_ms": 5000,
        "end_ms": 20000,
    },
    {
        "id": "ml-a2-s2",
        "record_id": REC_ML_AUDIO2,
        "kind": "audio",
        "sequence_no": 1,
        "content": "建立索引时需要进行分词，中文分词的质量直接影响检索效果。",
        "start_ms": 20000,
        "end_ms": 35000,
    },
    {
        "id": "ml-en-s1",
        "record_id": REC_ML_DOC,
        "kind": "document",
        "sequence_no": 0,
        "content": "The Transformer architecture relies entirely on self-attention "
        "mechanisms to draw global dependencies between input and output "
        "tokens in parallel.",
        "page_no": 1,
    },
    {
        "id": "ml-en-s2",
        "record_id": REC_ML_DOC,
        "kind": "document",
        "sequence_no": 1,
        "content": "Multi-head attention allows the model to jointly attend to "
        "information from different representation subspaces at different "
        "positions.",
        "page_no": 2,
    },
    {
        "id": "ml-en-s3",
        "record_id": REC_ML_DOC,
        "kind": "document",
        "sequence_no": 2,
        "content": "Compared to recurrent layers, self-attention reduces the sequential "
        "computation required for training, enabling significantly faster "
        "parallelization.",
        "page_no": 3,
    },
    {
        "id": "db-a1-s1",
        "record_id": REC_DB_AUDIO,
        "kind": "audio",
        "sequence_no": 0,
        "content": "数据库索引最常见的结构是 B+ 树，它把磁盘 IO 次数控制在树的高度以内。",
        "start_ms": 5000,
        "end_ms": 20000,
    },
    {
        "id": "db-a1-s2",
        "record_id": REC_DB_AUDIO,
        "kind": "audio",
        "sequence_no": 1,
        "content": "在查询优化器看来，走索引还是全表扫描取决于候选集的大小与统计信息。",
        "start_ms": 20000,
        "end_ms": 35000,
    },
    {
        "id": "db-d1-s1",
        "record_id": REC_DB_DOC,
        "kind": "document",
        "sequence_no": 0,
        "content": "多版本并发控制（MVCC）通过保存数据的历史版本来实现读写互不阻塞。",
        "page_no": 12,
    },
    {
        "id": "db-d1-s2",
        "record_id": REC_DB_DOC,
        "kind": "document",
        "sequence_no": 1,
        "content": "读已提交与可重复读是两种常见的事务隔离级别，前者避免脏读，"
        "后者进一步避免不可重复读。",
        "page_no": 13,
    },
    {
        "id": "u-s1",
        "record_id": REC_GLOBAL_DOC,
        "kind": "document",
        "sequence_no": 0,
        "content": "费曼学习法的核心是用最简单的语言把概念讲给外行听，"
        "讲不清楚的地方就是没学懂的地方。",
        "page_no": 1,
    },
    {
        "id": "ml-del-s1",
        "record_id": REC_ML_DELETED,
        "kind": "audio",
        "sequence_no": 0,
        "content": "支持向量机通过寻找最大间隔超平面来完成分类，核技巧把线性不可分"
        "问题映射到高维空间。",
        "start_ms": 5000,
        "end_ms": 20000,
    },
]

SEGMENT_BY_ID = {segment["id"]: segment for segment in SEGMENTS}
RECORD_BY_ID = {record["id"]: record for record in RECORDS}

CONCEPTS: list[ConceptFixture] = [
    {
        "id": CONCEPT_GD,
        "course_id": COURSE_ML,
        "name": "梯度下降",
        "description": "通过迭代更新参数最小化损失函数的优化算法",
    },
    {
        "id": CONCEPT_BP,
        "course_id": COURSE_ML,
        "name": "反向传播",
        "description": "利用链式法则逐层计算梯度的算法",
    },
    # 跨 Course 同名概念：两课程各有一个「索引」，语义与归属课程不同。
    {
        "id": CONCEPT_IDX_ML,
        "course_id": COURSE_ML,
        "name": "索引",
        "description": "信息检索中组织文档的数据结构，典型代表是倒排索引",
    },
    {
        "id": CONCEPT_IDX_DB,
        "course_id": COURSE_DB,
        "name": "索引",
        "description": "数据库中加速查询的数据结构，典型代表是 B+ 树",
    },
]

# 黄金集查询（工单 01 冻结）：expected = 人工判定的应命中分片（ground truth）。
# 正例 17 条（含概念桥接同义、跨 Course 同名、英文词形边界）；负例 3 条（无答案）。
QUERIES: list[QueryFixture] = [
    {
        "id": "P1",
        "query": "反向传播",
        "scope": "ML",
        "dimension": "zh-exact",
        "expected": ("ml-a1-s1",),
        "note": "中文精确词",
    },
    {
        "id": "P2",
        "query": "链式法则",
        "scope": "ML",
        "dimension": "zh-exact",
        "expected": ("ml-a1-s1",),
        "note": "中文精确词（分片无概念名亦有词面重叠）",
    },
    {
        "id": "P3",
        "query": "学习率",
        "scope": "ML",
        "dimension": "zh-exact",
        "expected": ("ml-a1-s3",),
        "note": "中文精确词",
    },
    {
        "id": "P4",
        "query": "优化算法",
        "scope": "ML",
        "dimension": "zh-synonym",
        "expected": ("ml-a1-s2",),
        "note": "概念桥接：查询只命中概念描述，扩展词召回分片",
    },
    {
        "id": "P5",
        "query": "索引",
        "scope": "ML",
        "dimension": "zh-cross-course",
        "expected": ("ml-a2-s1", "ml-a2-s2"),
        "note": "跨课程同名概念：ML 范围不得混入 DB 命中",
    },
    {
        "id": "P6",
        "query": "self-attention",
        "scope": "ML",
        "dimension": "en-exact",
        "expected": ("ml-en-s1", "ml-en-s3"),
        "note": "英文词形精确（含连字符两侧一致拆分）",
    },
    {
        "id": "P7",
        "query": "multi-head attention",
        "scope": "ML",
        "dimension": "en-exact",
        "expected": ("ml-en-s2",),
        "note": "英文多词 AND",
    },
    {
        "id": "P8",
        "query": "parallel",
        "scope": "ML",
        "dimension": "en-exact",
        "expected": ("ml-en-s1",),
        "note": "parallelization 不含 parallel 词形，正确不命中",
    },
    {
        "id": "P9",
        "query": "reduce sequential computation",
        "scope": "ML",
        "dimension": "en-inflection",
        "expected": ("ml-en-s3",),
        "note": "已知词形边界：分片为 reduces，FTS 无词干归一预期未命中（词汇错配样本）",
    },
    {
        "id": "P10",
        "query": "B+ 树",
        "scope": "DB",
        "dimension": "zh-exact",
        "expected": ("db-a1-s1", "db-a1-s2"),
        "note": "命中 B+ 树分片；概念「索引」描述含 B+ 树触发扩展带回查询优化分片",
    },
    {
        "id": "P11",
        "query": "事务隔离级别",
        "scope": "DB",
        "dimension": "zh-exact",
        "expected": ("db-d1-s2",),
        "note": "文档分片中文精确词",
    },
    {
        "id": "P12",
        "query": "MVCC",
        "scope": "DB",
        "dimension": "zh-exact",
        "expected": ("db-d1-s1",),
        "note": "英文缩写混排中文正文",
    },
    {
        "id": "P13",
        "query": "索引",
        "scope": "DB",
        "dimension": "zh-cross-course",
        "expected": ("db-a1-s1", "db-a1-s2"),
        "note": "跨课程同名概念：DB 范围不得混入 ML 命中",
    },
    {
        "id": "P14",
        "query": "索引",
        "scope": "ALL",
        "dimension": "zh-cross-course",
        "expected": ("ml-a2-s1", "ml-a2-s2", "db-a1-s1", "db-a1-s2"),
        "note": "ALL 含两课程同名概念，扩展词按概念归属课程分别执行",
    },
    {
        "id": "P15",
        "query": "费曼学习法",
        "scope": "ALL",
        "dimension": "zh-paraphrase",
        "expected": ("u-s1",),
        "note": "未归类全局资料仅 ALL 可见",
    },
    {
        "id": "P16",
        "query": "把概念讲给外行听",
        "scope": "ALL",
        "dimension": "zh-paraphrase",
        "expected": ("u-s1",),
        "note": "口语化改写但保留词面重叠",
    },
    {
        "id": "P17",
        "query": "attention",
        "scope": "ALL",
        "dimension": "en-exact",
        "expected": ("ml-en-s1", "ml-en-s2", "ml-en-s3"),
        "note": "英文宽词在 ALL 范围",
    },
    {
        "id": "N1",
        "query": "费曼学习法",
        "scope": "ML",
        "dimension": "no-answer-scope",
        "expected": (),
        "note": "证据只在未归类资料：COURSE 范围必须答「未找到」",
    },
    {
        "id": "N2",
        "query": "支持向量机",
        "scope": "ML",
        "dimension": "no-answer-deleted",
        "expected": (),
        "note": "证据只在软删记录：索引行存在也必须零命中",
    },
    {
        "id": "N3",
        "query": "量子计算",
        "scope": "ALL",
        "dimension": "no-answer-absent",
        "expected": (),
        "note": "语料中不存在：不得编造命中",
    },
]

SCOPE_COURSE_ID: dict[str, str | None] = {"ML": COURSE_ML, "DB": COURSE_DB, "ALL": None}

# 各范围允许命中的记录（软删记录任何范围都不允许）。
SCOPE_ALLOWED_RECORDS: dict[str, set[str]] = {
    "ML": {REC_ML_AUDIO1, REC_ML_AUDIO2, REC_ML_DOC},
    "DB": {REC_DB_AUDIO, REC_DB_DOC},
    "ALL": {REC_ML_AUDIO1, REC_ML_AUDIO2, REC_ML_DOC, REC_DB_AUDIO, REC_DB_DOC, REC_GLOBAL_DOC},
}


@asynccontextmanager
async def running_eval_app(data_dir: Path) -> AsyncGenerator[FastAPI]:
    # 评测走 service 层直调（不发 HTTP），只挂 lifespan 跑迁移与启动任务。
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        yield app


async def seed_corpus(app: FastAPI) -> None:
    async with app.state.session_factory() as session, session.begin():
        for course_id, name in ((COURSE_ML, "机器学习导论"), (COURSE_DB, "数据库系统")):
            await session.execute(
                text(
                    "INSERT INTO courses (id, name, learning_context, depth, status, "
                    "created_at, updated_at) "
                    "VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)"
                ),
                {"id": course_id, "name": name, "now": NOW},
            )
        for record in RECORDS:
            await session.execute(
                text(
                    "INSERT INTO records (id, course_id, capture_type, title, status, "
                    "duration_ms, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :course_id, :capture_type, :title, 'COMPLETED', 60000, "
                    ":now, :now, :deleted_at)"
                ),
                {
                    "id": record["id"],
                    "course_id": record["course_id"],
                    "capture_type": record["capture_type"],
                    "title": record["title"],
                    "now": NOW,
                    "deleted_at": "2026-09-18T00:00:00.000000Z" if record["deleted"] else None,
                },
            )
        # 音频分片宿主：每记录一个 file + transcript（带时间轴的正例形态）。
        audio_records = {
            record["id"] for record in RECORDS if record["capture_type"] == "RECORDING"
        }
        for index, record_id in enumerate(sorted(audio_records)):
            file_id = f"efile-{index}"
            transcript_id = f"etranscript-{index}"
            await session.execute(
                text(
                    "INSERT INTO record_files (id, record_id, file_type, source_type, "
                    "file_path, original_name, mime_type, file_size, duration_ms, "
                    "sequence_no, content_hash, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'p.ogg', 'p.ogg', "
                    "'audio/ogg', 1, 60000, 0, 'h', :now, :now, NULL)"
                ),
                {"id": file_id, "record_id": record_id, "now": NOW},
            )
            await session.execute(
                text(
                    "INSERT INTO transcripts (id, record_id, language, content, "
                    "source_version, edited_by_user, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 'zh-CN', '语料占位', 1, 0, :now, :now, NULL)"
                ),
                {"id": transcript_id, "record_id": record_id, "now": NOW},
            )
            for segment in SEGMENTS:
                if segment["kind"] != "audio" or segment["record_id"] != record_id:
                    continue
                await session.execute(
                    text(
                        "INSERT INTO transcript_segments (id, transcript_id, record_id, "
                        "file_id, sequence_no, record_start_ms, record_end_ms, "
                        "file_start_ms, file_end_ms, speaker, content, content_hash) "
                        "VALUES (:id, :transcript_id, :record_id, :file_id, :sequence_no, "
                        ":start_ms, :end_ms, :start_ms, :end_ms, NULL, :content, "
                        ":content_hash)"
                    ),
                    {
                        "id": segment["id"],
                        "transcript_id": transcript_id,
                        "record_id": record_id,
                        "file_id": file_id,
                        "sequence_no": segment["sequence_no"],
                        "start_ms": segment["start_ms"],
                        "end_ms": segment["end_ms"],
                        "content": segment["content"],
                        "content_hash": content_hash(segment["content"]),
                    },
                )
        # 文档分片宿主：每文档记录一个 DOCUMENT record_file。
        document_records = {
            record["id"] for record in RECORDS if record["capture_type"] != "RECORDING"
        }
        doc_file_by_record = {
            record_id: f"efile-doc-{index}"
            for index, record_id in enumerate(sorted(document_records))
        }
        for record_id, file_id in doc_file_by_record.items():
            await session.execute(
                text(
                    "INSERT INTO record_files (id, record_id, file_type, source_type, "
                    "file_path, original_name, mime_type, file_size, duration_ms, "
                    "sequence_no, content_hash, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 'DOCUMENT', 'UPLOADED', 'd.pdf', 'd.pdf', "
                    "'application/pdf', 1, 0, 0, 'h', :now, :now, NULL)"
                ),
                {"id": file_id, "record_id": record_id, "now": NOW},
            )
        for segment in SEGMENTS:
            if segment["kind"] != "document":
                continue
            await session.execute(
                text(
                    "INSERT INTO document_segments (id, course_id, record_id, "
                    "record_file_id, course_material_id, sequence_no, page_no, "
                    "section_title, content, start_offset, end_offset, content_hash) "
                    "VALUES (:id, :course_id, :record_id, :file_id, NULL, :sequence_no, "
                    ":page_no, NULL, :content, 0, 0, :content_hash)"
                ),
                {
                    "id": segment["id"],
                    "course_id": RECORD_BY_ID[segment["record_id"]]["course_id"],
                    "record_id": segment["record_id"],
                    "file_id": doc_file_by_record[segment["record_id"]],
                    "sequence_no": segment["sequence_no"],
                    "page_no": segment["page_no"],
                    "content": segment["content"],
                    "content_hash": content_hash(segment["content"]),
                },
            )
        for concept in CONCEPTS:
            await session.execute(
                text(
                    "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                    "description, concept_type, importance, status, source, created_at, "
                    "updated_at) "
                    "VALUES (:id, :course_id, :name, :normalized, :description, 'TERM', 3, "
                    "'CONFIRMED', 'AI_EXTRACTED', :now, :now)"
                ),
                {
                    "id": concept["id"],
                    "course_id": concept["course_id"],
                    "name": concept["name"],
                    "normalized": normalize_concept_name(concept["name"]),
                    "description": concept["description"],
                    "now": NOW,
                },
            )
        # 软删记录的分片同样建索引行（真实形态：软删不清索引，查询期过滤）。
        await SegmentSearchService.upsert_segment_index(
            session,
            ENTITY_TRANSCRIPT_SEGMENT,
            [segment["id"] for segment in SEGMENTS if segment["kind"] == "audio"],
        )
        await SegmentSearchService.upsert_segment_index(
            session,
            ENTITY_DOCUMENT_SEGMENT,
            [segment["id"] for segment in SEGMENTS if segment["kind"] == "document"],
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_CONCEPT, [concept["id"] for concept in CONCEPTS]
        )


async def baseline_retrieve(app: FastAPI, scope: str, query: str) -> list[LibrarySegmentSearchHit]:
    """V1 冻结基线链：概念 FTS 命中 → 原查询 + 扩展词并跑 → 合并去重。

    与 agent 工具 search_library 的差异仅为无 LIKE 兜底与无 JSON 载荷
    （服务契约管线按 spec 不含迁移期兜底）；数值常量直接复用工具冻结值。
    """
    course_id = SCOPE_COURSE_ID[scope]
    async with app.state.session_factory() as session:
        concepts = await CourseBrainService.match_concepts(
            session, course_id, query, CONCEPT_MATCH_LIMIT
        )
        terms: list[tuple[str, str | None, int]] = [(query, course_id, SEARCH_LIBRARY_LIMIT)]
        terms.extend(
            (concept.canonical_name, concept.course_id, SEARCH_LIBRARY_LIMIT)
            for concept in concepts
        )
        seen: set[tuple[str, str]] = set()
        merged: list[LibrarySegmentSearchHit] = []
        for term, scope_course_id, per_term_limit in terms:
            for hit in await SegmentSearchService.search_scope_segments(
                session, scope_course_id, term, per_term_limit
            ):
                key = (hit.record_id, hit.content)
                if key not in seen:
                    seen.add(key)
                    merged.append(hit)
        return merged[:SEARCH_LIBRARY_LIMIT]


async def run_all_queries(
    app: FastAPI,
) -> dict[str, list[LibrarySegmentSearchHit]]:
    return {
        fixture["id"]: await baseline_retrieve(app, fixture["scope"], fixture["query"])
        for fixture in QUERIES
    }


def positive_fixtures() -> list[QueryFixture]:
    return [fixture for fixture in QUERIES if fixture["expected"]]


def negative_fixtures() -> list[QueryFixture]:
    return [fixture for fixture in QUERIES if not fixture["expected"]]


async def golden_results(tmp_path: Path) -> dict[str, list[LibrarySegmentSearchHit]]:
    """建库 → 种子语料 → 跑全部黄金集查询，返回 查询id → 命中列表。"""
    async with running_eval_app(tmp_path / "KnowRealm") as app:
        await seed_corpus(app)
        return await run_all_queries(app)


@pytest.mark.anyio
async def test_eval_recall_at_k(tmp_path: Path) -> None:
    """Recall@8（宏平均）：正例查询的期望分片命中比例，阈值 0.90。"""
    results = await golden_results(tmp_path)
    recalls: list[float] = []
    failures: list[str] = []
    for fixture in positive_fixtures():
        hit_ids = [hit.segment_id for hit in results[fixture["id"]]]
        recall = len(set(fixture["expected"]) & set(hit_ids)) / len(fixture["expected"])
        recalls.append(recall)
        if recall < 1.0:
            missed = set(fixture["expected"]) - set(hit_ids)
            failures.append(f"{fixture['id']}({fixture['dimension']}) 缺 {sorted(missed)}")
        print(f"recall@8 {fixture['id']} {fixture['dimension']}: {recall:.3f}")
    macro = sum(recalls) / len(recalls)
    print(f"Recall@8 宏平均 = {macro:.3f}（阈值 {RECALL_AT_8_THRESHOLD}）")
    assert macro >= RECALL_AT_8_THRESHOLD, f"未达冻结阈值；未命中：{failures}"


@pytest.mark.anyio
async def test_eval_mrr(tmp_path: Path) -> None:
    """MRR：正例查询首个期望命中的倒数排名均值，阈值 0.90。"""
    results = await golden_results(tmp_path)
    reciprocals: list[float] = []
    for fixture in positive_fixtures():
        hit_ids = [hit.segment_id for hit in results[fixture["id"]]]
        rank = next(
            (
                index + 1
                for index, segment_id in enumerate(hit_ids)
                if segment_id in fixture["expected"]
            ),
            None,
        )
        reciprocal = 0.0 if rank is None else 1.0 / rank
        reciprocals.append(reciprocal)
        print(f"mrr {fixture['id']}: first_rank={rank} rr={reciprocal:.3f}")
    mrr = sum(reciprocals) / len(reciprocals)
    print(f"MRR = {mrr:.3f}（阈值 {MRR_THRESHOLD}）")
    assert mrr >= MRR_THRESHOLD


@pytest.mark.anyio
async def test_eval_no_answer_accuracy(tmp_path: Path) -> None:
    """无答案准确率：负例查询必须零证据命中（阈值 1.0，零容忍假阳性）。"""
    results = await golden_results(tmp_path)
    correct = 0
    for fixture in negative_fixtures():
        hits = results[fixture["id"]]
        if not hits:
            correct += 1
        else:
            print(
                f"假阳性 {fixture['id']}({fixture['dimension']}): "
                f"{[hit.segment_id for hit in hits]}"
            )
    accuracy = correct / len(negative_fixtures())
    print(f"无答案准确率 = {accuracy:.3f}（阈值 {NO_ANSWER_ACCURACY_THRESHOLD}）")
    assert accuracy >= NO_ANSWER_ACCURACY_THRESHOLD


@pytest.mark.anyio
async def test_eval_citation_verbatim(tmp_path: Path) -> None:
    """引用正确率：全部命中的 quote 与语料逐字一致 + 归属标题与定位信息正确。"""
    results = await golden_results(tmp_path)
    checked = 0
    for fixture in QUERIES:
        for hit in results[fixture["id"]]:
            segment = SEGMENT_BY_ID[hit.segment_id]
            record = RECORD_BY_ID[hit.record_id]
            assert hit.content == segment["content"], (
                f"{fixture['id']}：quote 非逐字回表（{hit.segment_id}）"
            )
            assert hit.record_title == record["title"], (
                f"{fixture['id']}：来源归属错误（{hit.segment_id}）"
            )
            if segment["kind"] == "audio":
                assert hit.record_start_ms == segment["start_ms"]
                assert hit.record_end_ms == segment["end_ms"]
                assert hit.page_no is None
            else:
                assert hit.page_no == segment["page_no"]
                assert hit.record_start_ms is None
            checked += 1
    print(f"引用逐字校验 {checked} 条命中全部通过（阈值 {CITATION_CORRECTNESS_THRESHOLD}）")
    # 实测基线 = 25（26 期望分片中 P9 词形边界设计内未命中）；跌破即回归。
    assert checked >= 25


@pytest.mark.anyio
async def test_eval_scope_isolation_no_leak(tmp_path: Path) -> None:
    """作用域硬门禁：任何查询不得返回范围外记录；负例查询零命中。"""
    results = await golden_results(tmp_path)
    leaks: list[str] = []
    for fixture in QUERIES:
        allowed = SCOPE_ALLOWED_RECORDS[fixture["scope"]]
        for hit in results[fixture["id"]]:
            if hit.record_id not in allowed:
                leaks.append(f"{fixture['id']}({fixture['scope']}) → {hit.record_id}")
    assert not leaks, f"范围泄漏：{leaks}"


@pytest.mark.anyio
async def test_eval_english_jieba_chain_conclusion(tmp_path: Path) -> None:
    """英文维度结论（冻结）：精确词形经 jieba 透传 + FTS5 unicode61 可召回；
    屈折变化（reduce≠reduces）是词面检索已知边界，作为词汇错配样本监测，
    不通过改分词器解决。"""
    results = await golden_results(tmp_path)
    en_exact = [fixture for fixture in QUERIES if fixture["dimension"] == "en-exact"]
    for fixture in en_exact:
        hit_ids = {hit.segment_id for hit in results[fixture["id"]]}
        assert hit_ids == set(fixture["expected"]), f"英文精确词形召回失败：{fixture['id']}"
    inflection = next(fixture for fixture in QUERIES if fixture["dimension"] == "en-inflection")
    hit_ids = {hit.segment_id for hit in results[inflection["id"]]}
    assert hit_ids == set(), "词形边界样例意外命中（若已加词干归一则需重冻结阈值）"
    # 归因断言：失败确因词形屈折（分片含 reduces、无 reduce 词元），非链路错误。
    target = SEGMENT_BY_ID[inflection["expected"][0]]
    assert target["content"].count("reduces") == 1
    assert "reduce " not in target["content"]
