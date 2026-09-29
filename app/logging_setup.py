import logging
import re
from contextvars import ContextVar

KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|AIza[A-Za-z0-9_\-]{20,}")
REDACTED = "[REDACTED]"
LOGGER_NAMES = ["", "uvicorn", "uvicorn.error", "uvicorn.access"]

current_llm_key = ContextVar("current_llm_key", default=None)


def redact(text):
    text = KEY_PATTERN.sub(REDACTED, text)

    key = current_llm_key.get()
    if key:
        text = text.replace(key, REDACTED)

    return text


class RedactKeysFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        redacted = redact(message)

        if redacted != message:
            record.msg = redacted
            record.args = None

        return True


def setup_logging():
    logging.basicConfig(level=logging.INFO)
    key_filter = RedactKeysFilter()

    for name in LOGGER_NAMES:
        for handler in logging.getLogger(name).handlers:
            handler.addFilter(key_filter)
