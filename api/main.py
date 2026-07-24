from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from db.session import engine
from exceptions import AppError, NotFoundError, OwnershipError, TierGateError
from middleware.auth import AuthMiddleware
from middleware.logging import configure_structlog

logger = structlog.get_logger(__name__)

# Defined before router imports so routers can `from main import limiter`
# without a circular-import failure.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_chat_per_hour}/hour"],
)

from routers import (  # noqa: E402
    calendar,
    chat,
    jobs,
    notifications,
    nutrition,
    pantry,
    plans,
    profile,
    recipes,
    shopping,
    webhooks,
)


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "unknown")


def _error_body(code: str, message: str, trace_id: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "trace_id": trace_id}}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_structlog()
    logger.info("api_ready", environment=settings.environment)
    yield
    await engine.dispose()
    logger.info("api_shutdown")


app = FastAPI(title="Nouri API", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    status_map: dict[type[AppError], int] = {
        NotFoundError: 404,
        OwnershipError: 404,
        TierGateError: 403,
    }
    status_code = status_map.get(type(exc), 400)
    return JSONResponse(
        status_code=status_code,
        content=_error_body(exc.code, exc.message, _trace_id(request)),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        error = detail["error"]
        code = str(error.get("code", "HTTP_ERROR")) if isinstance(error, dict) else "HTTP_ERROR"
        message = (
            str(error.get("message", exc.detail))
            if isinstance(error, dict)
            else str(exc.detail)
        )
    else:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, message, _trace_id(request)),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_body(
            "VALIDATION_ERROR",
            "Request validation failed",
            _trace_id(request),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_ERROR",
            "An unexpected error occurred",
            _trace_id(request),
        ),
    )


API_V1 = "/api/v1"

# Mount at API root — each router defines full OpenAPI paths (/profile, /plans, …).
app.include_router(profile.router, prefix=API_V1, tags=["profile"])
app.include_router(plans.router, prefix=API_V1, tags=["plans"])
app.include_router(recipes.router, prefix=API_V1, tags=["recipes"])
app.include_router(nutrition.router, prefix=API_V1, tags=["nutrition"])
app.include_router(chat.router, prefix=API_V1, tags=["chat"])
app.include_router(shopping.router, prefix=API_V1, tags=["shopping"])
app.include_router(pantry.router, prefix=API_V1, tags=["pantry"])
app.include_router(calendar.router, prefix=API_V1, tags=["calendar"])
app.include_router(notifications.router, prefix=API_V1, tags=["notifications"])
app.include_router(jobs.router, prefix=API_V1, tags=["jobs"])
app.include_router(webhooks.router, prefix=API_V1, tags=["webhooks"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
