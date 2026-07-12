from fastapi import FastAPI

from app.api.routers.health import router as health_router
from app.api.routers.me import router as me_router
from app.infrastructure.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="Atlas API")
    app.include_router(health_router)
    app.include_router(me_router)

    return app


app = create_app()
