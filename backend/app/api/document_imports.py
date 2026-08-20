from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.document import DocumentImportAccepted
from app.services.document_import_service import DocumentImportService

router = APIRouter(
    prefix="/api/document-imports",
    tags=["document-imports"],
    dependencies=[Depends(require_launch_token)],
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        507: {"model": ErrorResponse},
    },
)


@router.post("", status_code=202, response_model=DocumentImportAccepted)
async def import_document(
    request: Request,
    course_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    session: AsyncSession = Depends(get_db),
) -> DocumentImportAccepted:
    return await DocumentImportService.create(
        session,
        request.app.state.data_dir,
        str(course_id),
        file,
    )
