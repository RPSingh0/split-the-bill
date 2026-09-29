import secrets
from http import HTTPStatus

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.config import settings
from app.errors import ApiError
from app.logging_setup import setup_logging
from app.routers.auth import router as auth_router
from app.routers.bill_actions import router as bill_actions_router
from app.routers.bills import router as bills_router
from app.routers.extract import router as extract_router

setup_logging()

app = FastAPI(title="Split the Bill API")


def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key is None:
        raise ApiError(401, "UNAUTHORIZED", "Missing API key")
    if not secrets.compare_digest(x_api_key.encode(), settings.fastapi_api_key.encode()):
        raise ApiError(401, "UNAUTHORIZED", "Invalid API key")


def error_response(status_code: int, code: str, message: str, extra: dict | None = None):
    body = {"code": code, "message": message}
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content={"error": body})


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return error_response(exc.status_code, exc.code, exc.message, exc.extra)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    error = exc.errors()[0]

    parts = []
    for part in error["loc"]:
        parts.append(str(part))
    location = ".".join(parts)

    return error_response(400, "BAD_REQUEST", f"{location}: {error['msg']}")


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return error_response(exc.status_code, HTTPStatus(exc.status_code).name, str(exc.detail))


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router, dependencies=[Depends(require_api_key)])
app.include_router(extract_router, dependencies=[Depends(require_api_key)])
app.include_router(bills_router, dependencies=[Depends(require_api_key)])
app.include_router(bill_actions_router, dependencies=[Depends(require_api_key)])
