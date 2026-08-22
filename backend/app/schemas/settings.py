from pydantic import BaseModel


class ExternalProcessingConsentOut(BaseModel):
    granted_at: str | None
