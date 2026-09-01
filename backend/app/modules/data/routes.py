from fastapi import APIRouter, Depends, Request

from app.modules.data.archive import export_archive, library_is_empty
from app.modules.data.schemas import (
    DataDirectoryExportOut,
    DataDirectoryExportRequest,
    DataDirectoryLibraryStateOut,
)
from app.shared.deps import require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get(
    "/data-directory/library-state",
    response_model=DataDirectoryLibraryStateOut,
)
async def get_data_directory_library_state(request: Request) -> DataDirectoryLibraryStateOut:
    empty = await library_is_empty(request.app.state.session_factory)
    return DataDirectoryLibraryStateOut(empty_library=empty)


@router.post("/data-directory/export", response_model=DataDirectoryExportOut)
async def export_data_directory(
    body: DataDirectoryExportRequest,
    request: Request,
) -> DataDirectoryExportOut:
    file_name = await export_archive(
        request.app.state.data_dir, include_secrets=body.include_secrets
    )
    return DataDirectoryExportOut(file_name=file_name)
