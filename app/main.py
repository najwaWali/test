from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router as api_router
from app.config import settings
from app.helpers.exceptions import TicketNotFoundError
from app.logging import RequestIdMiddleware, configure_logging

OPENAPI_TAGS = [
    {"name": "health", "description": "Service liveness and dependency checks."},
    {"name": "tickets", "description": "Create and query support tickets."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    yield


def _error(status_code: int, detail: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})


def create_app() -> FastAPI:
    app = FastAPI(
        title="Loura Ticket Classifier",
        version="0.1.0",
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(api_router)

    @app.exception_handler(TicketNotFoundError)
    async def ticket_not_found_handler(request: Request, exc: TicketNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, str(exc), "ticket_not_found")

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # pydantic exception is overwhelming to understand
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(x) for x in first.get("loc", ())) or "request"
        msg = first.get("msg", "invalid request")
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{loc}: {msg}", "validation_error")

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "error"
        return _error(exc.status_code, detail, "http_error")

    return app


app = create_app()
