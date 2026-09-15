"""Course Brain HTTP 路由（F4 CB-03）：快照 / 概念列表 / 详情 / 来源 / 手动创建。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.course_brain.schemas import (
    BrainBuildAcceptedOut,
    BrainConceptCreate,
    BrainConceptDetailOut,
    BrainConceptListQuery,
    BrainConceptOut,
    BrainSnapshotOut,
    ConceptSourcesOut,
)
from app.modules.course_brain.service import CourseBrainService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/courses",
    tags=["course-brain"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{course_id}/brain", response_model=BrainSnapshotOut)
async def get_course_brain(
    course_id: str,
    session: AsyncSession = Depends(get_db),
) -> BrainSnapshotOut:
    return await CourseBrainService.get_snapshot(session, course_id)


@router.post(
    "/{course_id}/brain/builds",
    response_model=BrainBuildAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_course_brain_build(
    course_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> BrainBuildAcceptedOut:
    job_id = await CourseBrainService.request_build(session, request.app.state.data_dir, course_id)
    return BrainBuildAcceptedOut(job_id=job_id)


@router.get("/{course_id}/brain/concepts", response_model=list[BrainConceptOut])
async def list_course_brain_concepts(
    course_id: str,
    filters: Annotated[BrainConceptListQuery, Query()],
    session: AsyncSession = Depends(get_db),
) -> list[BrainConceptOut]:
    return await CourseBrainService.list_concepts(session, course_id, filters)


@router.get("/{course_id}/brain/concepts/{concept_id}", response_model=BrainConceptDetailOut)
async def get_course_brain_concept(
    course_id: str,
    concept_id: str,
    session: AsyncSession = Depends(get_db),
) -> BrainConceptDetailOut:
    return await CourseBrainService.get_concept(session, course_id, concept_id)


@router.get(
    "/{course_id}/brain/concepts/{concept_id}/sources",
    response_model=ConceptSourcesOut,
)
async def get_course_brain_concept_sources(
    course_id: str,
    concept_id: str,
    session: AsyncSession = Depends(get_db),
) -> ConceptSourcesOut:
    return await CourseBrainService.get_concept_sources(session, course_id, concept_id)


@router.post("/{course_id}/brain/concepts", response_model=BrainConceptOut, status_code=201)
async def create_course_brain_concept(
    course_id: str,
    payload: BrainConceptCreate,
    session: AsyncSession = Depends(get_db),
) -> BrainConceptOut:
    return await CourseBrainService.create_concept(session, course_id, payload)
