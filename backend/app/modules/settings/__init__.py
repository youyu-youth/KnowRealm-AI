"""设置平台模块：providers.json / settings.json 读写、外部处理同意与偏好。"""

from app.modules.settings.config import (
    LlmProviderConfig,
    TencentAsrConfig,
    external_processing_consent_at,
    grant_external_processing_consent,
    grant_llm_consent,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
    load_preferences,
    load_tencent_asr_config,
    load_tencent_asr_provider,
    save_llm_provider,
    save_preferences,
    save_tencent_asr_provider,
)

__all__ = [
    "LlmProviderConfig",
    "TencentAsrConfig",
    "external_processing_consent_at",
    "grant_external_processing_consent",
    "grant_llm_consent",
    "llm_consent",
    "llm_provider_fingerprint",
    "load_llm_provider",
    "load_preferences",
    "load_tencent_asr_config",
    "load_tencent_asr_provider",
    "save_llm_provider",
    "save_preferences",
    "save_tencent_asr_provider",
]
