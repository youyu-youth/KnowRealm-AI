"""文档解析产物：全文 text（transcripts.content 的该文件原文，逐字节同现状）
+ 内容块切片（document_segments 的定位层，F1 票 03）。

blocks JSONL 与音频句流（sentences.py）同机制：writeback 落盘缓存、
finalizer 事务内读回建分片，崩溃恢复路径可重建。
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from zipfile import is_zipfile

import pymupdf
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError  # pyright: ignore[reportUnknownVariableType]

from app.modules.jobs.schemas import ProcessingJobErrorCode


class DocumentParseError(Exception):
    def __init__(self, code: ProcessingJobErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class DocumentBlock:
    """内容块：content 为全文 text 的精确切片，start/end_offset 即其字符偏移。"""

    content: str
    page_no: int | None = None
    start_offset: int = 0
    end_offset: int = 0


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    blocks: list[DocumentBlock]


def extract_text_file(path: Path) -> str:
    try:
        content = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentParseError(ProcessingJobErrorCode.NON_UTF8_TEXT) from None
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    return content


# 段落 = 非空行起、至空行（连续换行）止的极大片段；段内保留单换行。
_PARAGRAPH = re.compile(r"[^\n]+(?:\n(?!\n)[^\n]+)*")


def blocks_from_plain_text(text: str) -> list[DocumentBlock]:
    """纯文本按空行切段；全空白段跳过。txt/md 解析与旧缓存降级共用。"""
    blocks: list[DocumentBlock] = []
    for match in _PARAGRAPH.finditer(text):
        if not match.group().strip():
            continue
        blocks.append(
            DocumentBlock(
                content=match.group(),
                start_offset=match.start(),
                end_offset=match.end(),
            )
        )
    return blocks


def extract_text(path: Path) -> ParsedDocument:
    content = extract_text_file(path)
    return ParsedDocument(text=content, blocks=blocks_from_plain_text(content))


def extract_pdf(path: Path) -> ParsedDocument:
    with path.open("rb") as source:
        signature = source.read(5)
    if signature != b"%PDF-":
        raise DocumentParseError(ProcessingJobErrorCode.FORMAT_MISMATCH)
    try:
        document = pymupdf.open(path)
    except pymupdf.FileDataError:
        raise DocumentParseError(ProcessingJobErrorCode.CORRUPT_DOCUMENT) from None
    try:
        # PyMuPDF 公开 API 的类型信息不完整；运行时值稳定为 bool/int 与纯文本 str。
        if cast(bool, document.needs_pass):  # pyright: ignore[reportUnknownMemberType]
            raise DocumentParseError(ProcessingJobErrorCode.PASSWORD_PROTECTED)
        blocks: list[DocumentBlock] = []
        parts: list[str] = []
        cursor = 0
        for index, page in enumerate(document):  # pyright: ignore[reportUnknownVariableType, reportArgumentType]
            page_text = cast(str, page.get_text("text")).strip()  # pyright: ignore[reportUnknownMemberType]
            if not page_text:
                continue
            if parts:
                cursor += len("\n\n")
            blocks.append(
                DocumentBlock(
                    content=page_text,
                    page_no=index + 1,
                    start_offset=cursor,
                    end_offset=cursor + len(page_text),
                )
            )
            parts.append(page_text)
            cursor += len(page_text)
        return ParsedDocument(text="\n\n".join(parts), blocks=blocks)
    finally:
        document.close()


def extract_docx(path: Path) -> ParsedDocument:
    if not is_zipfile(path):
        raise DocumentParseError(ProcessingJobErrorCode.FORMAT_MISMATCH)
    try:
        document = Document(str(path))
    except (KeyError, PackageNotFoundError, ValueError, XMLSyntaxError):
        raise DocumentParseError(ProcessingJobErrorCode.CORRUPT_DOCUMENT) from None
    blocks: list[DocumentBlock] = []
    parts: list[str] = []
    cursor = 0
    for block in document.iter_inner_content():
        text: str
        if isinstance(block, Paragraph):
            text = block.text
            if not text.strip():
                continue
        else:
            rows = ["\t".join(cell.text for cell in row.cells) for row in block.rows]
            text = "\n".join(row for row in rows if row.strip())
            if not text:
                continue
        if parts:
            cursor += len("\n")
        blocks.append(
            DocumentBlock(content=text, start_offset=cursor, end_offset=cursor + len(text))
        )
        parts.append(text)
        cursor += len(text)
    return ParsedDocument(text="\n".join(parts), blocks=blocks)


def extract_document(path: Path) -> ParsedDocument:
    extension = path.suffix.lower()
    if extension in {".txt", ".md"}:
        parsed = extract_text(path)
    elif extension == ".pdf":
        parsed = extract_pdf(path)
    elif extension == ".docx":
        parsed = extract_docx(path)
    else:
        raise DocumentParseError(ProcessingJobErrorCode.FORMAT_MISMATCH)
    if not parsed.text.strip():
        raise DocumentParseError(ProcessingJobErrorCode.NO_EXTRACTABLE_TEXT)
    return parsed


def block_line(block: DocumentBlock) -> str:
    return json.dumps(
        {
            "content": block.content,
            "page_no": block.page_no,
            "start_offset": block.start_offset,
            "end_offset": block.end_offset,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_blocks_jsonl(raw: str) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        blocks.append(
            DocumentBlock(
                content=str(data["content"]),
                page_no=data.get("page_no"),
                start_offset=data["start_offset"],
                end_offset=data["end_offset"],
            )
        )
    return blocks


def read_blocks_jsonl(path: Path) -> list[DocumentBlock]:
    return parse_blocks_jsonl(path.read_text(encoding="utf-8"))


def write_blocks_jsonl(path: Path, blocks: list[DocumentBlock]) -> None:
    path.write_text("\n".join(block_line(block) for block in blocks), encoding="utf-8")
