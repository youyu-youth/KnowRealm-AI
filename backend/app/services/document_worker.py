import asyncio
import json
from pathlib import Path
from typing import cast

from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.document import ProcessingJob, RecordFile, Transcript
from app.models.record import Record
from app.schemas.document import ProcessingJobErrorCode
from app.services.document_parser import DocumentParseError, extract_document_text

ERROR_MESSAGES = {
    ProcessingJobErrorCode.NON_UTF8_TEXT: "文本文件不是 UTF-8 编码",
    ProcessingJobErrorCode.CORRUPT_DOCUMENT: "文档已损坏，无法读取",
    ProcessingJobErrorCode.PASSWORD_PROTECTED: "文档受密码保护，无法读取",
    ProcessingJobErrorCode.FORMAT_MISMATCH: "文件内容与扩展名不匹配",
    ProcessingJobErrorCode.NO_EXTRACTABLE_TEXT: "文档没有可提取的文本",
    ProcessingJobErrorCode.TEMPORARY_IO: "文档暂时无法读取",
    ProcessingJobErrorCode.INTERNAL_ERROR: "文档处理失败",
}


class DocumentWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        while not self._stopped.is_set():
            if await self._process_one():
                continue
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.05)
            except TimeoutError:
                pass

    async def _process_one(self) -> bool:
        claimed = await self._claim_one()
        if claimed is None:
            return False
        job_id, record_id, path = claimed
        try:
            content = await asyncio.to_thread(extract_document_text, path)
        except DocumentParseError as exc:
            await self._fail(job_id, record_id, exc.code)
        except OSError:
            await self._fail(job_id, record_id, ProcessingJobErrorCode.TEMPORARY_IO)
        except Exception:
            logger.error(
                "document_parse_failed",
                job_id=job_id,
                record_id=record_id,
                error_code=ProcessingJobErrorCode.INTERNAL_ERROR,
            )
            await self._fail(job_id, record_id, ProcessingJobErrorCode.INTERNAL_ERROR)
        else:
            await self._succeed(job_id, record_id, content)
        return True

    async def _claim_one(self) -> tuple[str, str, Path] | None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = (
                await session.scalars(
                    select(ProcessingJob)
                    .where(
                        ProcessingJob.job_type == "DOCUMENT_PARSE",
                        ProcessingJob.status == "PENDING",
                        or_(
                            ProcessingJob.next_run_at.is_(None),
                            ProcessingJob.next_run_at <= now,
                        ),
                    )
                    .order_by(ProcessingJob.created_at)
                    .limit(1)
                )
            ).one_or_none()
            if job is None or job.record_id is None:
                return None
            result = cast(
                CursorResult[tuple[()]],
                await session.execute(
                    update(ProcessingJob)
                    .where(ProcessingJob.id == job.id, ProcessingJob.status == "PENDING")
                    .values(
                        status="RUNNING",
                        attempts=ProcessingJob.attempts + 1,
                        started_at=now,
                        updated_at=now,
                    )
                ),
            )
            if result.rowcount != 1:
                return None
            input_data: object = json.loads(job.input_json)
            if not isinstance(input_data, dict):
                return job.id, job.record_id, Path()
            input_dict = cast(dict[str, object], input_data)
            record_file_id = input_dict.get("record_file_id")
            if not isinstance(record_file_id, str):
                return job.id, job.record_id, Path()
            record_file = await session.get(RecordFile, record_file_id)
            if record_file is None:
                return job.id, job.record_id, Path()
            path = (self._data_dir / record_file.file_path).resolve()
            files_root = (self._data_dir / "files").resolve()
            if not path.is_relative_to(files_root):
                return job.id, job.record_id, Path()
            return job.id, job.record_id, path

    async def _succeed(self, job_id: str, record_id: str, content: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            if job is None or record is None or job.status != "RUNNING":
                return
            session.add(
                Transcript(
                    record_id=record_id,
                    language="und",
                    content=content,
                    source_version=1,
                    edited_by_user=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            job.status = "SUCCEEDED"
            job.progress = 1
            job.finished_at = now
            job.updated_at = now
            record.status = "SUMMARY_PENDING"
            record.updated_at = now
            await session.flush()

    async def _fail(
        self,
        job_id: str,
        record_id: str,
        code: ProcessingJobErrorCode,
    ) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            if job is None or record is None or job.status != "RUNNING":
                return
            job.status = "FAILED"
            job.error_code = code.value
            job.error_message = ERROR_MESSAGES[code]
            job.finished_at = now
            job.updated_at = now
            record.status = "FAILED"
            record.updated_at = now
            await session.flush()
