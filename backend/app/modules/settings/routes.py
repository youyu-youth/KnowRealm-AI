import asyncio
from typing import cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.modules.llm.service import SummaryGenerationError, call_summary_model
from app.modules.settings.config import (
    external_processing_consent_at,
    grant_external_processing_consent,
    grant_llm_consent,
    llm_consent,
    load_llm_provider,
    load_preferences,
    load_tencent_asr_config,
    load_tencent_asr_provider,
    save_llm_provider,
    save_preferences,
    save_tencent_asr_provider,
)
from app.modules.settings.schemas import (
    ExternalProcessingConsentOut,
    LlmConsentOut,
    LlmProviderOut,
    LlmProviderStateOut,
    LlmProviderTestOut,
    LlmProviderUpdate,
    LlmUsageOut,
    PreferencesOut,
    PreferencesUpdate,
    TencentAsrProviderOut,
    TencentAsrProviderStateOut,
    TencentAsrProviderUpdate,
    TencentAsrTestOut,
)
from app.modules.settings.usage import llm_usage
from app.modules.transcript.integrations.tencent import (
    TencentAsrApiError,
    TencentAsrClient,
    TencentAsrCredentials,
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


def _provider_out(base_url: str, api_key: str, model: str) -> LlmProviderOut:
    return LlmProviderOut(
        base_url=base_url,
        model=model,
        has_api_key=bool(api_key),
        api_key_hint=f"••••{api_key[-4:]}" if api_key else None,
    )


def _tencent_asr_out(
    secret_id: str,
    secret_key: str,
    region: str,
) -> TencentAsrProviderOut:
    return TencentAsrProviderOut(
        region=region,
        has_credentials=bool(secret_id and secret_key),
        secret_id_hint=f"••••{secret_id[-4:]}" if secret_id else None,
    )


def _asr_test_error_detail(code: str) -> str:
    if code.startswith("AuthFailure"):
        return "腾讯云凭据校验未通过，请检查 SecretId / SecretKey"
    if code == "FailedOperation.UserNotRegistered":
        return "凭据有效，但该账号尚未开通语音识别服务"
    if code == "FailedOperation.ServiceIsolate":
        return "凭据有效，但账号已欠费停服，请检查腾讯云余额"
    return f"腾讯云语音识别服务返回错误：{code}"


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


@router.get("/providers/tencent-asr", response_model=TencentAsrProviderStateOut)
async def get_tencent_asr_provider(request: Request) -> TencentAsrProviderStateOut:
    provider = await asyncio.to_thread(load_tencent_asr_provider, request.app.state.data_dir)
    return TencentAsrProviderStateOut(
        provider=(
            _tencent_asr_out(provider.secret_id, provider.secret_key, provider.region)
            if provider is not None
            else None
        )
    )


@router.put("/providers/tencent-asr", response_model=TencentAsrProviderStateOut)
async def put_tencent_asr_provider(
    body: TencentAsrProviderUpdate,
    request: Request,
) -> TencentAsrProviderStateOut:
    provider = await asyncio.to_thread(
        save_tencent_asr_provider,
        request.app.state.data_dir,
        secret_id=body.secret_id,
        secret_key=body.secret_key,
        region=body.region,
        clear_secret_key=body.clear_secret_key,
    )
    return TencentAsrProviderStateOut(
        provider=_tencent_asr_out(provider.secret_id, provider.secret_key, provider.region)
    )


@router.post("/providers/tencent-asr/tests", response_model=TencentAsrTestOut)
async def test_tencent_asr_provider(request: Request) -> TencentAsrTestOut:
    config = await asyncio.to_thread(load_tencent_asr_config, request.app.state.data_dir)
    if config is None:
        raise HTTPException(status_code=409, detail="请先配置腾讯云语音识别密钥")
    client = cast(TencentAsrClient, request.app.state.asr_client)
    try:
        await client.test_credentials(
            TencentAsrCredentials(
                secret_id=config.secret_id,
                secret_key=config.secret_key,
                region=config.region,
            )
        )
    except TencentAsrApiError as exc:
        raise HTTPException(status_code=502, detail=_asr_test_error_detail(exc.code)) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502, detail="无法连接腾讯云语音识别服务，请检查网络"
        ) from exc
    return TencentAsrTestOut(ok=True, region=config.region)


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


@router.get("/usage/llm", response_model=LlmUsageOut)
async def get_llm_usage(request: Request) -> LlmUsageOut:
    return await llm_usage(request.app.state.session_factory)
