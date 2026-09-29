import logging

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.config import settings
from app.llm.base import (
    IMAGE_INSTRUCTION,
    PROMPT,
    ReceiptExtraction,
    bad_output,
    content_blocked,
    key_invalid,
    quota_exceeded,
    receipt_text_message,
    timeout,
    unavailable,
)

logger = logging.getLogger(__name__)

TIMEOUT_MILLISECONDS = 45000

BLOCKED_FINISH_REASONS = [
    types.FinishReason.SAFETY,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.SPII,
    types.FinishReason.IMAGE_SAFETY,
    types.FinishReason.IMAGE_PROHIBITED_CONTENT,
]


def contents(image, mime, text):
    if image is None:
        return receipt_text_message(text)

    return [types.Part.from_bytes(data=image, mime_type=mime), IMAGE_INSTRUCTION]


def is_bad_key_message(error):
    return error.code == 400 and "api key" in str(error.message).lower()


def map_gemini_error(error):
    logger.warning("Gemini call failed: %s", error)

    if error.code == 401 or error.code == 403 or is_bad_key_message(error):
        return key_invalid()

    if error.code == 429:
        return quota_exceeded()

    if error.code >= 500:
        return unavailable(retryable=True)

    return unavailable()


def is_blocked(response):
    if response.prompt_feedback is not None and response.prompt_feedback.block_reason is not None:
        return True

    if not response.candidates:
        return False

    return response.candidates[0].finish_reason in BLOCKED_FINISH_REASONS


class GeminiProvider:
    def __init__(self, api_key):
        http_options = types.HttpOptions(timeout=TIMEOUT_MILLISECONDS)
        self.client = genai.Client(api_key=api_key, http_options=http_options)

    def call(self, image, mime, text):
        config = types.GenerateContentConfig(
            system_instruction=PROMPT,
            response_mime_type="application/json",
            response_schema=ReceiptExtraction,
        )

        try:
            return self.client.models.generate_content(
                model=settings.gemini_model,
                contents=contents(image, mime, text),
                config=config,
            )
        except errors.APIError as error:
            raise map_gemini_error(error)
        except httpx.TimeoutException:
            raise timeout()
        except httpx.TransportError:
            raise unavailable(retryable=True)

    def extract(self, image, mime, text):
        response = self.call(image, mime, text)

        if is_blocked(response):
            raise content_blocked()

        if response.text is None:
            raise bad_output()

        try:
            return ReceiptExtraction.model_validate_json(response.text)
        except ValidationError:
            raise bad_output()
