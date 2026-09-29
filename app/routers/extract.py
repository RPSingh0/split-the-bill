from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from app.auth import current_user
from app.errors import ApiError
from app.extraction import build_extract_result
from app.llm.base import extract_with_retry
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAIProvider
from app.logging_setup import current_llm_key
from app.models import User
from app.schemas import ExtractResponse

router = APIRouter(tags=["extract"])

PROVIDERS = {"openai": OpenAIProvider, "gemini": GeminiProvider}
IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TEXT_CHARS = 10000


def bad_request(message):
    return ApiError(400, "BAD_REQUEST", message)


async def get_provider(
    x_llm_provider: str | None = Header(default=None),
    x_llm_key: str | None = Header(default=None),
):
    if x_llm_provider not in PROVIDERS:
        raise bad_request("Choose OpenAI or Gemini as the provider")

    if x_llm_key is None or x_llm_key.strip() == "":
        raise bad_request("Paste your API key")

    current_llm_key.set(x_llm_key)
    provider_class = PROVIDERS[x_llm_provider]

    return provider_class(x_llm_key)


def read_image(file):
    if file.content_type not in IMAGE_TYPES:
        raise bad_request("Please use a JPEG or PNG photo")

    image = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(image) > MAX_IMAGE_BYTES:
        raise bad_request("The photo must be 4 MB or smaller")

    return image


def check_text(text):
    if len(text) > MAX_TEXT_CHARS:
        raise bad_request("Pasted text must be 10,000 characters or fewer")


def check_one_input(file, text):
    if file is not None and text is not None:
        raise bad_request("Send either a photo or pasted text, not both")

    if file is None and text is None:
        raise bad_request("Send a photo or paste the receipt text")


@router.post("/extract", response_model=ExtractResponse)
def extract(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    user: User = Depends(current_user),
    provider=Depends(get_provider),
):
    if text is not None and text.strip() == "":
        text = None

    check_one_input(file, text)

    image = None
    mime = None
    if file is not None:
        image = read_image(file)
        mime = file.content_type
    else:
        check_text(text)

    extraction = extract_with_retry(provider, image, mime, text)

    return build_extract_result(extraction.model_dump())
