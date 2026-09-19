# jieba 无类型存根（纯 Python、随包分发词典）：本文件是唯一接触点，
# 关闭其符号的 unknown 检查，隔离在适配层内。
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

"""jieba 应用层分词：索引侧与查询侧共用同一 `cut_for_search`（ADR-0016）。

索引文本为切词后空格拼接，FTS5 默认 unicode61 tokenizer 以空白分界、
将每个词保持为整体 token，从而获得中文词级匹配。
"""

from collections.abc import Iterable

import jieba


def tokenize(text: str) -> str:
    """切词并空格拼接为 FTS5 索引文本。"""
    return " ".join(token for token in jieba.cut_for_search(text) if token.strip())


def match_expression(query: str) -> str | None:
    """构建 FTS5 MATCH 表达式：每个词引号包裹（内部引号双写），空格连接为 AND。

    过滤经 FTS5 tokenizer 后为空的纯符号词；全部无效时返回 None（调用方按空结果处理）。
    """
    terms = []
    for token in _query_terms(query):
        escaped = token.replace('"', '""')
        terms.append(f'"{escaped}"')
    return " ".join(terms) or None


def _query_terms(query: str) -> Iterable[str]:
    for token in jieba.cut_for_search(query):
        token = token.strip()
        if token and any(character.isalnum() for character in token):
            yield token


def warmup() -> None:
    """预加载 jieba 词典（首次约 0.5~1s），避免首搜卡顿。"""
    jieba.initialize()


def escape_like(needle: str) -> str:
    r"""LIKE 转义（%/_/反斜杠）：导航级子串查询共用（library 列表搜索、agent 兜底）。"""
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
