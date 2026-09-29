from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.errors import ApiError

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "extract_v1.md"
PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

IMAGE_INSTRUCTION = "Transcribe this receipt photo."


class ExtractedItem(BaseModel):
    name: str
    quantity: float | None
    unit_price: float | None
    line_total: float | None


class ExtractedCharge(BaseModel):
    label: str
    kind: Literal["tax", "service_charge", "discount", "round_off", "tip", "other"]
    rate_percent: float | None
    amount: float | None


class ReceiptExtraction(BaseModel):
    is_receipt: bool
    merchant: str | None
    date: str | None
    currency: str | None
    items: list[ExtractedItem]
    subtotal: float | None
    charges: list[ExtractedCharge]
    total: float | None
    warnings: list[str]


class LLMError(ApiError):
    def __init__(self, status_code, code, message, retryable=False):
        super().__init__(status_code, code, message)
        self.retryable = retryable


def key_invalid():
    return LLMError(400, "LLM_KEY_INVALID", "The provider rejected this API key")


def quota_exceeded():
    return LLMError(429, "LLM_QUOTA_EXCEEDED", "Your quota or rate limit with the provider has been reached")


def content_blocked():
    return LLMError(400, "LLM_CONTENT_BLOCKED", "The provider refused to read this input")


def timeout():
    return LLMError(504, "LLM_TIMEOUT", "The provider took too long to respond", retryable=True)


def unavailable(retryable=False):
    return LLMError(502, "LLM_UNAVAILABLE", "The provider is unavailable right now", retryable)


def bad_output():
    return LLMError(502, "LLM_BAD_OUTPUT", "The provider's answer could not be read")


def receipt_text_message(text):
    return f"Receipt text:\n<receipt>\n{text}\n</receipt>"


def extract_with_retry(provider, image, mime, text):
    try:
        return provider.extract(image, mime, text)
    except LLMError as error:
        if not error.retryable:
            raise

    return provider.extract(image, mime, text)
