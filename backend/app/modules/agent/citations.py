"""挂载对话回答的引用块解析与逐字校验（纯函数，独立可测）。

条目分流：引用行内含 URL 视为网络来源（web 条目，仅非空检查、不逐字校验，
B1）；否则按转写摘录走逐字校验路径（record 条目）。
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.modules.transcript.sentences import sentences_from_plain_text

# 引用块约定：正文 [1][2] 角标，文末每行「[n] 转写原文摘录」（web 条目为
# 「[n] 标题 — URL」），摘录 ≤80 字。引用行行首允许模型常见的 markdown 前缀
# （> 引用、-/* 列表），前缀不进摘录。
CITATION_QUOTE_MAX_CHARS = 80
CITATION_LINE_RE = re.compile(r"^(?:>\s*)?(?:[-*]\s*)*\[(\d{1,3})\]\s*(.+)$")
# 意译摘录兜底对齐的最低相似度：低于它的「最佳匹配句」视为无可靠出处，丢弃。
CITATION_ALIGN_MIN_RATIO = 0.65
# web 引用行内 URL 的识别与尾部标点清理（URL 按约定位于行尾，容忍句读粘带）。
WEB_URL_RE = re.compile(r"https?://[^\s（）()\[\]{}<>＞]+")
WEB_URL_TRAILING_PUNCT = "。，,；;！!？?、"


@dataclass(frozen=True)
class ParsedReply:
    """挂载对话回答的解析结果：正文已剥离引用块，引用仅含通过校验的条目。"""

    content: str
    citations: list[dict[str, int | str]]


def _normalize_for_align(text: str) -> str:
    """对齐比对的归一化：去空白与 markdown 强调符，只留内容字符。"""
    return re.sub(r"[\s*]+", "", text)


def _align_quote(quote: str, transcript: str) -> str | None:
    """意译摘录的兜底对齐：在转写行中找最相似句，达标则返回真实原句。

    - 相似度基于归一化文本（去空白与 ``**`` 排版）逐行 ``SequenceMatcher`` 比对；
    - 返回值必然是 transcript 的连续子串（原句 ≤80 字，超长时以最长公共片段
      为锚取 ≤80 字窗口），保证落库 quote 与前端「分片 content 包含 quote」
      的句级定位链天然一致；
    - 最佳相似度低于 CITATION_ALIGN_MIN_RATIO 时返回 None，按无可靠出处丢弃。
    """
    normalized_quote = _normalize_for_align(quote)
    if not normalized_quote:
        return None
    best_line: str | None = None
    best_ratio = 0.0
    for line in sentences_from_plain_text(transcript):
        normalized_line = _normalize_for_align(line.text)
        if not normalized_line:
            continue
        matcher = SequenceMatcher(None, normalized_quote, normalized_line, autojunk=False)
        if matcher.real_quick_ratio() < CITATION_ALIGN_MIN_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_line = line.text
    if best_line is None or best_ratio < CITATION_ALIGN_MIN_RATIO:
        return None
    if len(best_line) <= CITATION_QUOTE_MAX_CHARS:
        return best_line
    anchor = SequenceMatcher(None, quote, best_line, autojunk=False).find_longest_match(
        0, len(quote), 0, len(best_line)
    )
    start = max(0, anchor.b - 20)
    return best_line[start : start + CITATION_QUOTE_MAX_CHARS]


def _web_entry(index: int, text: str) -> dict[str, int | str] | None:
    """含 URL 的引用行 → web 条目：title 取剥除 URL 与分隔符后的剩余文本。

    只做非空检查（url/title 任一为空即丢弃），不做逐字校验（B1 决策 6）。
    """
    match = WEB_URL_RE.search(text)
    if match is None:
        return None
    url = match.group(0).rstrip(WEB_URL_TRAILING_PUNCT)
    title = re.sub(r"[\s\-—–:：·|]+$", "", (text[: match.start()] + text[match.end() :]).strip())
    if not url or not title:
        return None
    return {"index": index, "source": "web", "url": url, "title": title}


def parse_citation_reply(text: str, *, transcript: str, record_id: str) -> ParsedReply:
    """从回答尾部识别「[n] 摘录」引用块：剥离入 citations，逐条校验。

    - 只有文末连续匹配引用行格式的部分才算引用块（行首容忍 > / - / * 等
      markdown 前缀），正文中的 [1] 角标不受影响；
    - 行内含 URL → web 条目（仅非空检查）；其余按转写摘录校验：逐字命中
      （≤80 字）直接保留，意译或超长的摘录经 ``_align_quote`` 在转写行中
      模糊对齐，达标则以真实原文替换展示；
    - 对齐不到可靠出处（或空、index<1）→ 整条丢弃不展示；
    - 引用块被识别即从展示正文剥离，即使全部条目未通过校验。
    """
    lines = text.rstrip().split("\n")
    cut = len(lines)
    entries: list[tuple[int, str]] = []
    while cut > 0:
        match = CITATION_LINE_RE.match(lines[cut - 1].strip())
        if match is None:
            break
        entries.append((int(match.group(1)), match.group(2).strip()))
        cut -= 1
    if not entries:
        return ParsedReply(content=text, citations=[])
    entries.reverse()
    citations: list[dict[str, int | str]] = []
    for index, quote in entries:
        if not quote or index < 1:
            continue
        web = _web_entry(index, quote)
        if web is not None:
            citations.append(web)
            continue
        if len(quote) <= CITATION_QUOTE_MAX_CHARS and quote in transcript:
            final_quote: str | None = quote
        else:
            final_quote = _align_quote(quote, transcript)
        if final_quote is not None:
            citations.append(
                {
                    "index": index,
                    "source": "record",
                    "record_id": record_id,
                    "quote": final_quote,
                }
            )
    return ParsedReply(content="\n".join(lines[:cut]).rstrip(), citations=citations)
