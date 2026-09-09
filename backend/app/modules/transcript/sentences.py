"""句级转写句子流的落盘与解析（ASR 管道与 finalizer 共享，票 04 复用行拆）。

JSONL 每行一句：{"text", "start_ms", "end_ms"}，时间戳可空（= 无时间轴
来源，全库唯一退化态）。纯文本行拆（降级 / 回填）产出的句子时间戳为 NULL。
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sentence:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


def sentence_line(sentence: Sentence) -> str:
    return json.dumps(
        {"text": sentence.text, "start_ms": sentence.start_ms, "end_ms": sentence.end_ms},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_sentences_jsonl(raw: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        sentences.append(
            Sentence(
                text=str(data["text"]),
                start_ms=data.get("start_ms"),
                end_ms=data.get("end_ms"),
            )
        )
    return sentences


def read_sentences_jsonl(path: Path) -> list[Sentence]:
    return parse_sentences_jsonl(path.read_text(encoding="utf-8"))


def write_sentences_jsonl(path: Path, sentences: list[Sentence]) -> None:
    path.write_text(
        "\n".join(sentence_line(sentence) for sentence in sentences), encoding="utf-8"
    )


def sentences_from_plain_text(text: str) -> list[Sentence]:
    """纯文本按行拆为无时间戳句子；空白行跳过（时间轴不陈列空句）。"""
    return [Sentence(text=line) for line in text.splitlines() if line.strip()]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
