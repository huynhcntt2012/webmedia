import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.admin_catalogue import router as admin_catalogue_router
from app.admin_comics import router as admin_comics_router
from app.auth import admin_router
from app.auth import router as auth_router
from app.body_limit import AuthBodyLimit
from app.catalogue import router as catalogue_router
from app.config import Settings, get_settings
from app.content_access import router as content_router
from app.database import make_engine
from app.dependencies import DependencyProbe
from app.payments import router as payments_router
from app.playback import router as playback_router
from app.reader import router as reader_router
from app.uploads import router as upload_router

logger = logging.getLogger("suni.requests")


def create_app(settings: Settings | None = None, probe=None) -> FastAPI:
    settings = settings or get_settings()
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    owned_probe = probe is None
    probe = probe or DependencyProbe(settings)
    auth_engine = make_engine(settings)
    auth_cache = Redis.from_url(
        settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        auth_engine.dispose()
        auth_cache.close()
        if owned_probe:
            probe.close()

    app = FastAPI(
        title="Suni AI Cinema API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts.split(","))
    app.add_middleware(AuthBodyLimit)
    app.state.settings = settings
    app.state.auth_engine = auth_engine
    app.state.auth_cache = auth_cache
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(admin_catalogue_router)
    app.include_router(admin_comics_router)
    app.include_router(upload_router)
    app.include_router(playback_router)
    app.include_router(reader_router)
    app.include_router(content_router)
    app.include_router(payments_router)
    app.include_router(catalogue_router)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # FastAPI's default includes raw input values, including rejected passwords.
        return JSONResponse(
            {
                "detail": "Thông tin không hợp lệ. Kiểm tra email, tên và mật khẩu (12–128 ký tự)."
                if request.url.path.startswith("/auth/")
                else "Tham số yêu cầu không hợp lệ."
            },
            status_code=422,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Do not serialize exceptions: connection strings and user inputs may contain secrets.
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "route": getattr(route, "path", "unmatched"),
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.get("/health/live", tags=["operations"])
    async def live():
        return {"status": "ok", "service": "suni-api"}

    @app.get("/health/ready", tags=["operations"])
    async def ready():
        async def check(operation):
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(operation),
                    timeout=settings.readiness_timeout_seconds,
                )
                return "ok"
            except Exception:
                return "unavailable"

        postgres, redis = await asyncio.gather(check(probe.postgres), check(probe.cache))
        healthy = postgres == redis == "ok"
        return JSONResponse(
            {
                "status": "ok" if healthy else "unavailable",
                "checks": {"postgres": postgres, "redis": redis},
            },
            status_code=200 if healthy else 503,
        )

    return app
