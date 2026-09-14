"""挂载对话回答的引用块解析与逐字校验（纯函数，独立可测）。

条目分流：引用行内含 URL 视为网络来源（web 条目，仅非空检查、不逐字校验，
B1）；否则按转写摘录走逐字校验路径（record 条目）。跨记录会话（B2）走
parse_library_citation_reply：「（来源：标题）」定位候选记录后逐字 / 模糊
校验，无候选才全范围逐字扫描兜底（禁止全范围模糊对齐，性能红线）。
"""

import re
from collections.abc import Sequence
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
# 跨记录引用行的来源标记：「[n] 摘录（来源：记录标题）」，容忍全 / 半角括号与
# 冒号变体；标题外层允许书名号包裹（照抄指令的常见走样）。
SOURCE_MARK_RE = re.compile(
    r"^(?P<quote>.+?)[（(]\s*来源\s*[:：]\s*(?P<title>.+?)[）)]$", re.DOTALL
)
TITLE_WRAP_CHARS = "《》\"“”'"


@dataclass(frozen=True)
class ParsedReply:
    """挂载对话回答的解析结果：正文已剥离引用块，引用仅含通过校验的条目。"""

    content: str
    citations: list[dict[str, int | str]]


@dataclass(frozen=True)
class LibraryRecordMaterial:
    """跨记录引用校验材料：记录标题与转写全文（标题定位与逐字校验的根基）。"""

    record_id: str
    title: str
    transcript: str


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
    lines, entries = _split_trailing_citation_lines(text)
    if not entries:
        return ParsedReply(content=text, citations=[])
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
    return ParsedReply(content="\n".join(lines).rstrip(), citations=citations)


def _split_trailing_citation_lines(text: str) -> tuple[list[str], list[tuple[int, str]]]:
    """识别文末连续引用行：返回（正文行, [(index, 行文本)]），无引用块时行文本为空列表。"""
    lines = text.rstrip().split("\n")
    cut = len(lines)
    entries: list[tuple[int, str]] = []
    while cut > 0:
        match = CITATION_LINE_RE.match(lines[cut - 1].strip())
        if match is None:
            break
        entries.append((int(match.group(1)), match.group(2).strip()))
        cut -= 1
    entries.reverse()
    return lines[:cut], entries


def _library_record_entry(
    index: int, quote: str, record: LibraryRecordMaterial
) -> dict[str, int | str]:
    return {
        "index": index,
        "source": "record",
        "record_id": record.record_id,
        "record_title": record.title,
        "quote": quote,
    }


def parse_library_citation_reply(
    text: str, records: Sequence[LibraryRecordMaterial]
) -> ParsedReply:
    """跨记录会话（COURSE/ALL）的引用块解析：归属由校验器裁定，模型只写标题。

    行分流：URL → web 条目（不逐字校验）；含「（来源：标题）」→ 标题等值定位
    候选记录，逐字命中（≤80 字）直接过（重名逐一验证取首过者），逐字不过仅在
    候选记录内模糊对齐（复用 _align_quote）；无来源标记 → 全范围逐字扫描取首
    包含者（禁止全范围模糊对齐，性能红线）。全部失败整条丢弃；引用块被识别
    即从展示正文剥离。
    """
    body_lines, entries = _split_trailing_citation_lines(text)
    if not entries:
        return ParsedReply(content=text, citations=[])
    citations: list[dict[str, int | str]] = []
    for index, line in entries:
        if not line or index < 1:
            continue
        web = _web_entry(index, line)
        if web is not None:
            citations.append(web)
            continue
        match = SOURCE_MARK_RE.match(line)
        if match is not None:
            quote = match.group("quote").strip()
            title = match.group("title").strip().strip(TITLE_WRAP_CHARS)
            candidates = [record for record in records if record.title == title]
            if quote and candidates:
                # 逐字验证按清单顺序取首过者；逐字不过才在候选内模糊对齐。
                entry = next(
                    (
                        _library_record_entry(index, quote, record)
                        for record in candidates
                        if len(quote) <= CITATION_QUOTE_MAX_CHARS and quote in record.transcript
                    ),
                    None,
                )
                if entry is None:
                    for record in candidates:
                        aligned = _align_quote(quote, record.transcript)
                        if aligned is not None:
                            entry = _library_record_entry(index, aligned, record)
                            break
                if entry is not None:
                    citations.append(entry)
                    continue
            # 来源标记存在但定位 / 校验失败：不做全范围兜底（标题不可信时归属不可裁定）。
            continue
        # 无来源标记：全范围逐字扫描取首包含者（仅逐字，不做模糊对齐）。
        if 0 < len(line) <= CITATION_QUOTE_MAX_CHARS:
            for record in records:
                if line in record.transcript:
                    citations.append(_library_record_entry(index, line, record))
                    break
    return ParsedReply(content="\n".join(body_lines).rstrip(), citations=citations)
