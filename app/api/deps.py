from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.graph_profile import GetMyProfileUseCase
from app.application.health import GetHealthStatusUseCase
from app.infrastructure.database import get_session
from app.infrastructure.graph_client import HttpxGraphClient
from app.infrastructure.health_repository import SqlAlchemyHealthCheckRepository
from app.infrastructure.obo_token_provider import MsalOboTokenProvider
from app.infrastructure.redis_client import redis_client

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_health_status_use_case(session: SessionDep) -> GetHealthStatusUseCase:
    repository = SqlAlchemyHealthCheckRepository(session)
    return GetHealthStatusUseCase(repository)


def get_my_profile_use_case() -> GetMyProfileUseCase:
    token_provider = MsalOboTokenProvider(redis_client)
    graph_client = HttpxGraphClient()
    return GetMyProfileUseCase(token_provider, graph_client)
