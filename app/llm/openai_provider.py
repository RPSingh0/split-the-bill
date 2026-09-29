import base64
import logging

import openai
from openai import OpenAI
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


def user_content(image, mime, text):
    if image is None:
        return receipt_text_message(text)

    encoded = base64.b64encode(image).decode("ascii")
    image_url = {"url": f"data:{mime};base64,{encoded}", "detail": "high"}

    return [
        {"type": "text", "text": IMAGE_INSTRUCTION},
        {"type": "image_url", "image_url": image_url},
    ]


def map_openai_error(error):
    logger.warning("OpenAI call failed: %s", error)

    if isinstance(error, openai.APITimeoutError):
        return timeout()

    if isinstance(error, openai.APIConnectionError):
        return unavailable(retryable=True)

    if isinstance(error, openai.AuthenticationError) or isinstance(error, openai.PermissionDeniedError):
        return key_invalid()

    if isinstance(error, openai.RateLimitError):
        return quota_exceeded()

    if isinstance(error, openai.BadRequestError) and error.code == "content_policy_violation":
        return content_blocked()

    if isinstance(error, openai.InternalServerError):
        return unavailable(retryable=True)

    return unavailable()


class OpenAIProvider:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key, timeout=45, max_retries=0)

    def call(self, image, mime, text):
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": user_content(image, mime, text)},
        ]

        try:
            return self.client.chat.completions.parse(
                model=settings.openai_model,
                messages=messages,
                temperature=0,
                response_format=ReceiptExtraction,
            )
        except openai.ContentFilterFinishReasonError:
            raise content_blocked()
        except openai.LengthFinishReasonError:
            raise bad_output()
        except ValidationError:
            raise bad_output()
        except openai.APIError as error:
            raise map_openai_error(error)

    def extract(self, image, mime, text):
        completion = self.call(image, mime, text)
        message = completion.choices[0].message

        if message.refusal:
            raise content_blocked()

        if message.parsed is None:
            raise bad_output()

        return message.parsed
