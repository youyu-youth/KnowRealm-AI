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


def extract_text_file(path: Path) -> str:
    try:
        content = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentParseError(ProcessingJobErrorCode.NON_UTF8_TEXT) from None
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    return content


def extract_pdf(path: Path) -> str:
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
        pages = [
            cast(str, page.get_text("text")).strip()  # pyright: ignore[reportUnknownMemberType]
            for page in document
        ]
        return "\n\n".join(page for page in pages if page)
    finally:
        document.close()


def extract_docx(path: Path) -> str:
    if not is_zipfile(path):
        raise DocumentParseError(ProcessingJobErrorCode.FORMAT_MISMATCH)
    try:
        document = Document(str(path))
    except (KeyError, PackageNotFoundError, ValueError, XMLSyntaxError):
        raise DocumentParseError(ProcessingJobErrorCode.CORRUPT_DOCUMENT) from None
    blocks: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text.strip():
                blocks.append(block.text)
        else:
            rows = ["\t".join(cell.text for cell in row.cells) for row in block.rows]
            table_text = "\n".join(row for row in rows if row.strip())
            if table_text:
                blocks.append(table_text)
    return "\n".join(blocks)


def extract_document_text(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".txt", ".md"}:
        content = extract_text_file(path)
    elif extension == ".pdf":
        content = extract_pdf(path)
    elif extension == ".docx":
        content = extract_docx(path)
    else:
        raise DocumentParseError(ProcessingJobErrorCode.FORMAT_MISMATCH)
    if not content.strip():
        raise DocumentParseError(ProcessingJobErrorCode.NO_EXTRACTABLE_TEXT)
    return content
