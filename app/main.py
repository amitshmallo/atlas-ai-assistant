from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.calendar import router as calendar_router
from app.api.routers.chat import router as chat_router
from app.api.routers.documents import router as documents_router
from app.api.routers.health import router as health_router
from app.api.routers.me import router as me_router
from app.infrastructure.config import settings
from app.infrastructure.logging import configure_logging
from app.infrastructure.telemetry import configure_telemetry


def create_app() -> FastAPI:
    configure_logging()
    configure_telemetry(service_name="atlas-api")

    app = FastAPI(title="Atlas API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Conversation-Id"],
    )
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(chat_router)
    app.include_router(calendar_router)
    app.include_router(documents_router)

    return app


app = create_app()
