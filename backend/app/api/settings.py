import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.agents.llm import SummaryGenerationError, call_summary_model
from app.api.deps import require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.settings import (
    ExternalProcessingConsentOut,
    LlmConsentOut,
    LlmProviderOut,
    LlmProviderStateOut,
    LlmProviderUpdate,
    PreferencesOut,
    PreferencesUpdate,
)
from app.schemas.summary import LlmProviderTestOut
from app.services.local_config import (
    external_processing_consent_at,
    grant_external_processing_consent,
    grant_llm_consent,
    llm_consent,
    load_llm_provider,
    load_preferences,
    save_llm_provider,
    save_preferences,
)

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


def _provider_out(base_url: str, api_key: str, model: str) -> LlmProviderOut:
    return LlmProviderOut(
        base_url=base_url,
        model=model,
        has_api_key=bool(api_key),
        api_key_hint=f"••••{api_key[-4:]}" if api_key else None,
    )


@router.get(
    "/external-processing-consents/tencent-asr",
    response_model=ExternalProcessingConsentOut,
)
async def get_tencent_asr_consent(request: Request) -> ExternalProcessingConsentOut:
    granted_at = await asyncio.to_thread(external_processing_consent_at, request.app.state.data_dir)
    return ExternalProcessingConsentOut(granted_at=granted_at)


@router.post(
    "/external-processing-consents/tencent-asr",
    response_model=ExternalProcessingConsentOut,
)
async def grant_tencent_asr_consent(request: Request) -> ExternalProcessingConsentOut:
    granted_at = await asyncio.to_thread(
        grant_external_processing_consent, request.app.state.data_dir
    )
    return ExternalProcessingConsentOut(granted_at=granted_at)


@router.get("/providers/llm", response_model=LlmProviderStateOut)
async def get_llm_provider(request: Request) -> LlmProviderStateOut:
    provider = await asyncio.to_thread(load_llm_provider, request.app.state.data_dir)
    return LlmProviderStateOut(
        provider=(
            _provider_out(provider.base_url, provider.api_key, provider.model)
            if provider is not None
            else None
        )
    )


@router.put("/providers/llm", response_model=LlmProviderStateOut)
async def put_llm_provider(
    body: LlmProviderUpdate,
    request: Request,
) -> LlmProviderStateOut:
    provider = await asyncio.to_thread(
        save_llm_provider,
        request.app.state.data_dir,
        base_url=body.base_url,
        api_key=body.api_key,
        model=body.model,
        clear_api_key=body.clear_api_key,
    )
    return LlmProviderStateOut(
        provider=_provider_out(provider.base_url, provider.api_key, provider.model)
    )


@router.get("/external-processing-consents/llm", response_model=LlmConsentOut)
async def get_llm_consent(request: Request) -> LlmConsentOut:
    granted_at, current = await asyncio.to_thread(llm_consent, request.app.state.data_dir)
    return LlmConsentOut(granted_at=granted_at, current=current)


@router.post("/external-processing-consents/llm", response_model=LlmConsentOut)
async def post_llm_consent(request: Request) -> LlmConsentOut:
    granted_at = await asyncio.to_thread(grant_llm_consent, request.app.state.data_dir)
    if granted_at is None:
        raise HTTPException(status_code=409, detail="请先配置包含密钥的 LLM Provider")
    return LlmConsentOut(granted_at=granted_at, current=True)


@router.get("/preferences", response_model=PreferencesOut)
async def get_preferences(request: Request) -> PreferencesOut:
    preferences = await asyncio.to_thread(load_preferences, request.app.state.data_dir)
    return PreferencesOut.model_validate(preferences)


@router.put("/preferences", response_model=PreferencesOut)
async def put_preferences(body: PreferencesUpdate, request: Request) -> PreferencesOut:
    updates = body.model_dump(exclude_unset=True)
    preferences = await asyncio.to_thread(save_preferences, request.app.state.data_dir, updates)
    return PreferencesOut.model_validate(preferences)


@router.post("/providers/llm/tests", response_model=LlmProviderTestOut)
async def test_llm_provider(request: Request) -> LlmProviderTestOut:
    provider = await asyncio.to_thread(load_llm_provider, request.app.state.data_dir)
    if provider is None or not provider.api_key:
        raise HTTPException(status_code=409, detail="请先配置包含密钥的 LLM Provider")
    prompt = (
        "这是连接测试使用的合成 Transcript，不包含用户资料。"
        "请按正式 Summary Schema 返回主题、500 至 1000 字摘要和至少一个章节。"
    )
    try:
        await call_summary_model(
            session_factory=request.app.state.session_factory,
            summary_model=request.app.state.summary_model,
            provider=provider,
            prompt=prompt,
            graph_name="summary_connection_test",
            graph_node="generate",
            prompt_version="summary-v1",
        )
    except SummaryGenerationError as exc:
        raise HTTPException(status_code=502, detail="Provider 未返回有效的 Summary 结构") from exc
    return LlmProviderTestOut(ok=True, model=provider.model)
