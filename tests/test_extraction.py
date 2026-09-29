import json
import logging
from pathlib import Path

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from app.auth import current_user
from app.llm.base import ReceiptExtraction, bad_output, content_blocked, key_invalid, quota_exceeded, timeout, unavailable
from app.llm.gemini_provider import map_gemini_error
from app.llm.openai_provider import map_openai_error
from app.logging_setup import RedactKeysFilter
from app.main import app
from app.routers.extract import PROVIDERS

SAMPLES = Path(__file__).parent.parent / "samples"
LLM_KEY = "sk-test-secret-key-1234567890"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

client = TestClient(app)


class FakeProvider:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def extract(self, image, mime, text):
        self.calls.append({"image": image, "mime": mime, "text": text})
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


class LeakyProvider:
    def __init__(self, api_key):
        self.api_key = api_key

    def extract(self, image, mime, text):
        logging.getLogger("app.test").warning("Calling the provider with key %s", self.api_key)
        raise key_invalid()


def fake_user():
    return {"id": "00000000-0000-0000-0000-000000000001", "username": "rupinder"}


@pytest.fixture(autouse=True)
def logged_in():
    app.dependency_overrides[current_user] = fake_user
    yield
    app.dependency_overrides.clear()


def use_fake(monkeypatch, outcomes):
    fake = FakeProvider(outcomes)

    def build(api_key):
        return fake

    monkeypatch.setitem(PROVIDERS, "openai", build)

    return fake


def load_sample(name):
    with open(SAMPLES / name, encoding="utf-8") as file:
        return json.load(file)


def extraction(llm_output):
    return ReceiptExtraction.model_validate(llm_output)


def sample_2():
    return extraction(load_sample("receipt_2.expected.json"))


def not_a_receipt():
    return extraction({
        "is_receipt": False,
        "merchant": None,
        "date": None,
        "currency": None,
        "items": [],
        "subtotal": None,
        "charges": [],
        "total": None,
        "warnings": [],
    })


def llm_headers(provider="openai", key=LLM_KEY):
    return {"X-API-Key": "test-api-key", "X-LLM-Provider": provider, "X-LLM-Key": key}


def post_text(text, headers=None):
    if headers is None:
        headers = llm_headers()

    return client.post("/extract", data={"text": text}, headers=headers)


def post_file(content, content_type, headers=None):
    if headers is None:
        headers = llm_headers()

    return client.post("/extract", files={"file": ("receipt", content, content_type)}, headers=headers)


def issue_codes(response):
    codes = []
    for entry in response.json()["issues"]:
        codes.append(entry["code"])

    return codes


def error_code(response):
    return response.json()["error"]["code"]


def openai_status_error(error_class, status_code):
    request = httpx2.Request("POST", OPENAI_URL)
    response = httpx2.Response(status_code, request=request)

    return error_class("failed", response=response, body=None)


def gemini_error(error_class, status_code, status, message):
    body = {"error": {"code": status_code, "status": status, "message": message}}

    return error_class(status_code, body)


def test_extract_text_returns_receipt_in_paise(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = post_text("THE CURRY LEAF\nButter Naan 4 60.00 240.00")

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["currency"] == "INR"
    assert receipt["bill_date"] == "2026-09-28"
    assert receipt["items"][0]["quantity"] == 4
    assert receipt["items"][0]["line_total_paise"] == 24000
    assert receipt["charges"][3]["amount_paise"] == -26
    assert receipt["total_paise"] == 137000
    assert response.json()["issues"] == []
    assert fake.calls[0]["image"] is None
    assert "THE CURRY LEAF" in fake.calls[0]["text"]


def test_extract_image_passes_bytes_and_type(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = post_file(b"fake-jpeg-bytes", "image/jpeg")

    assert response.status_code == 200
    assert fake.calls[0]["image"] == b"fake-jpeg-bytes"
    assert fake.calls[0]["mime"] == "image/jpeg"
    assert fake.calls[0]["text"] is None


def test_amount_with_more_than_two_decimals_is_rounded_and_flagged(monkeypatch):
    llm_output = load_sample("receipt_2.expected.json")
    llm_output["items"][0]["line_total"] = 240.005
    use_fake(monkeypatch, [extraction(llm_output)])

    response = post_text("receipt")

    assert response.json()["receipt"]["items"][0]["line_total_paise"] == 24001
    assert "INVALID_AMOUNT" in issue_codes(response)


def test_printed_tip_moves_to_suggested_tip_and_out_of_total(monkeypatch):
    llm_output = load_sample("receipt_2.expected.json")
    llm_output["charges"].append({"label": "Tip", "kind": "tip", "rate_percent": None, "amount": 100.00})
    llm_output["total"] = 1470.00
    use_fake(monkeypatch, [extraction(llm_output)])

    response = post_text("receipt")

    receipt = response.json()["receipt"]
    assert receipt["suggested_tip_paise"] == 10000
    assert receipt["total_paise"] == 137000
    assert len(receipt["charges"]) == 4
    assert response.json()["issues"] == []


def test_invalid_date_becomes_null(monkeypatch):
    llm_output = load_sample("receipt_2.expected.json")
    llm_output["date"] = "28/09/2026"
    use_fake(monkeypatch, [extraction(llm_output)])

    response = post_text("receipt")

    assert response.json()["receipt"]["bill_date"] is None


def test_not_a_receipt(monkeypatch):
    use_fake(monkeypatch, [not_a_receipt()])

    response = post_text("hello there")

    assert response.status_code == 200
    assert issue_codes(response) == ["NOT_A_RECEIPT"]


@pytest.mark.parametrize(
    "make_error, status_code, code",
    [
        (key_invalid, 400, "LLM_KEY_INVALID"),
        (quota_exceeded, 429, "LLM_QUOTA_EXCEEDED"),
        (content_blocked, 400, "LLM_CONTENT_BLOCKED"),
        (timeout, 504, "LLM_TIMEOUT"),
        (unavailable, 502, "LLM_UNAVAILABLE"),
        (bad_output, 502, "LLM_BAD_OUTPUT"),
    ],
)
def test_provider_errors_are_returned_as_error_codes(monkeypatch, make_error, status_code, code):
    use_fake(monkeypatch, [make_error(), make_error()])

    response = post_text("receipt")

    assert response.status_code == status_code
    assert error_code(response) == code
    assert LLM_KEY not in response.text


def test_timeout_is_retried_once(monkeypatch):
    fake = use_fake(monkeypatch, [timeout(), sample_2()])

    response = post_text("receipt")

    assert response.status_code == 200
    assert len(fake.calls) == 2


def test_timeout_twice_gives_up(monkeypatch):
    fake = use_fake(monkeypatch, [timeout(), timeout(), sample_2()])

    response = post_text("receipt")

    assert response.status_code == 504
    assert len(fake.calls) == 2


def test_unavailable_after_connection_error_is_retried(monkeypatch):
    fake = use_fake(monkeypatch, [unavailable(retryable=True), sample_2()])

    response = post_text("receipt")

    assert response.status_code == 200
    assert len(fake.calls) == 2


def test_key_error_is_not_retried(monkeypatch):
    fake = use_fake(monkeypatch, [key_invalid(), sample_2()])

    response = post_text("receipt")

    assert error_code(response) == "LLM_KEY_INVALID"
    assert len(fake.calls) == 1


def test_quota_error_is_not_retried(monkeypatch):
    fake = use_fake(monkeypatch, [quota_exceeded(), sample_2()])

    response = post_text("receipt")

    assert error_code(response) == "LLM_QUOTA_EXCEEDED"
    assert len(fake.calls) == 1


def test_both_file_and_text_is_rejected(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = client.post(
        "/extract",
        data={"text": "receipt"},
        files={"file": ("receipt", b"bytes", "image/jpeg")},
        headers=llm_headers(),
    )

    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"
    assert fake.calls == []


def test_neither_file_nor_text_is_rejected(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = post_text("   ")

    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"
    assert fake.calls == []


def test_unknown_provider_is_rejected():
    response = post_text("receipt", headers=llm_headers(provider="anthropic"))

    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"


def test_missing_llm_key_is_rejected():
    headers = {"X-API-Key": "test-api-key", "X-LLM-Provider": "openai"}

    response = post_text("receipt", headers=headers)

    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"


def test_file_too_large_is_rejected(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = post_file(b"x" * (4 * 1024 * 1024 + 1), "image/jpeg")

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "The photo must be 4 MB or smaller"
    assert fake.calls == []


def test_heic_photo_is_rejected(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = post_file(b"heic-bytes", "image/heic")

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Please use a JPEG or PNG photo"
    assert fake.calls == []


def test_text_too_long_is_rejected(monkeypatch):
    fake = use_fake(monkeypatch, [sample_2()])

    response = post_text("x" * 10001)

    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"
    assert fake.calls == []


def test_api_key_is_required():
    headers = {"X-LLM-Provider": "openai", "X-LLM-Key": LLM_KEY}

    response = post_text("receipt", headers=headers)

    assert response.status_code == 401
    assert error_code(response) == "UNAUTHORIZED"


def test_login_is_required():
    app.dependency_overrides.clear()

    response = post_text("receipt")

    assert response.status_code == 401
    assert error_code(response) == "UNAUTHORIZED"


def test_llm_key_never_appears_in_logs_or_response(monkeypatch, caplog):
    plain_key = "plain-secret-key-42"
    monkeypatch.setitem(PROVIDERS, "openai", LeakyProvider)
    caplog.handler.addFilter(RedactKeysFilter())
    caplog.set_level(logging.INFO)

    response = post_text("receipt", headers=llm_headers(key=plain_key))

    assert error_code(response) == "LLM_KEY_INVALID"
    assert plain_key not in response.text
    assert plain_key not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_key_shaped_strings_are_redacted():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "keys %s and %s", ("sk-abcdefghijklmnop", "AIzaSyA1234567890abcdefghijk"), None)

    RedactKeysFilter().filter(record)

    assert record.getMessage() == "keys [REDACTED] and [REDACTED]"


def test_map_openai_errors():
    request = httpx2.Request("POST", OPENAI_URL)

    assert map_openai_error(openai_status_error(openai.AuthenticationError, 401)).code == "LLM_KEY_INVALID"
    assert map_openai_error(openai_status_error(openai.PermissionDeniedError, 403)).code == "LLM_KEY_INVALID"
    assert map_openai_error(openai_status_error(openai.RateLimitError, 429)).code == "LLM_QUOTA_EXCEEDED"
    assert map_openai_error(openai_status_error(openai.NotFoundError, 404)).code == "LLM_UNAVAILABLE"
    assert not map_openai_error(openai_status_error(openai.NotFoundError, 404)).retryable

    server_error = map_openai_error(openai_status_error(openai.InternalServerError, 500))
    assert server_error.code == "LLM_UNAVAILABLE"
    assert server_error.retryable

    timeout_error = map_openai_error(openai.APITimeoutError(request=request))
    assert timeout_error.code == "LLM_TIMEOUT"
    assert timeout_error.retryable

    connection_error = map_openai_error(openai.APIConnectionError(request=request))
    assert connection_error.code == "LLM_UNAVAILABLE"
    assert connection_error.retryable


def test_map_gemini_errors():
    bad_key = gemini_error(genai_errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")
    bad_request = gemini_error(genai_errors.ClientError, 400, "INVALID_ARGUMENT", "Request contains an invalid argument.")
    denied = gemini_error(genai_errors.ClientError, 403, "PERMISSION_DENIED", "Permission denied.")
    quota = gemini_error(genai_errors.ClientError, 429, "RESOURCE_EXHAUSTED", "Quota exceeded.")
    overloaded = gemini_error(genai_errors.ServerError, 503, "UNAVAILABLE", "The model is overloaded.")

    assert map_gemini_error(bad_key).code == "LLM_KEY_INVALID"
    assert map_gemini_error(denied).code == "LLM_KEY_INVALID"
    assert map_gemini_error(quota).code == "LLM_QUOTA_EXCEEDED"
    assert map_gemini_error(bad_request).code == "LLM_UNAVAILABLE"
    assert not map_gemini_error(bad_request).retryable
    assert map_gemini_error(overloaded).code == "LLM_UNAVAILABLE"
    assert map_gemini_error(overloaded).retryable
