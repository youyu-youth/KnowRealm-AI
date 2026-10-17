"""计划练习的启动时题面副本（ADR-0029）。

frozen_json 保存题型、题干、选项、参考答案、解析、难度、概念归属与来源
身份；轮次内读题、判分与评分一律走副本，原题后续修改/删除/移出课程不
影响已开始轮次。普通模拟测试无副本，仍实时读原题（兼容分支）。
"""

import json
from typing import cast

from pydantic import BaseModel, ConfigDict

from app.modules.quiz.models import Quiz, QuizTestItem


class FrozenFace(BaseModel):
    """判分与展示共用的题面；quiz_id 仅追溯，不用于读取内容。"""

    model_config = ConfigDict(extra="forbid")

    question_type: str
    stem: str
    options: list[str]
    correct_answer: str
    explanation: str
    difficulty: str
    concept_id: str | None = None
    record_id: str
    record_title: str
    # 原题身份快照：quiz_test_items.quiz_id 物理删除置空后仍可追溯。
    quiz_id: str
    quiz_version: str = ""


def freeze(quiz: Quiz, record_title: str, quiz_version: str) -> str:
    return json.dumps(
        FrozenFace(
            question_type=quiz.question_type,
            stem=quiz.stem,
            options=cast(list[str], json.loads(quiz.options_json)),
            correct_answer=quiz.correct_answer_json,
            explanation=quiz.explanation,
            difficulty=quiz.difficulty,
            concept_id=quiz.concept_id,
            record_id=quiz.record_id,
            record_title=record_title,
            quiz_id=quiz.id,
            quiz_version=quiz_version,
        ).model_dump(),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def face_of(item: QuizTestItem, quiz: Quiz | None) -> FrozenFace:
    """轮次题面：冻结副本优先；普通测试（无副本）读原题。"""
    if item.frozen_json is not None:
        return FrozenFace.model_validate_json(item.frozen_json)
    assert quiz is not None, "无冻结副本的卷面题必须仍有原题"
    return FrozenFace(
        question_type=quiz.question_type,
        stem=quiz.stem,
        options=cast(list[str], json.loads(quiz.options_json)),
        correct_answer=quiz.correct_answer_json,
        explanation=quiz.explanation,
        difficulty=quiz.difficulty,
        concept_id=quiz.concept_id,
        record_id=quiz.record_id,
        record_title="",
        quiz_id=quiz.id,
    )
