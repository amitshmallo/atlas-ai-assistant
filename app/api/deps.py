from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.chat import SendChatMessageUseCase
from app.application.create_calendar_event import CreateCalendarEventUseCase
from app.application.graph_profile import GetMyProfileUseCase
from app.application.graph_tools import GraphToolExecutor
from app.application.health import GetHealthStatusUseCase
from app.infrastructure.chat_client import AzureOpenAIChatClient
from app.infrastructure.conversation_repository import SqlAlchemyConversationRepository
from app.infrastructure.database import get_session
from app.infrastructure.graph_calendar_client import HttpxGraphCalendarClient
from app.infrastructure.graph_client import HttpxGraphClient
from app.infrastructure.graph_mail_client import HttpxGraphMailClient
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


@lru_cache
def _get_chat_client() -> AzureOpenAIChatClient:
    return AzureOpenAIChatClient()


def get_send_chat_message_use_case(session: SessionDep) -> SendChatMessageUseCase:
    conversation_repository = SqlAlchemyConversationRepository(session, redis_client)
    token_provider = MsalOboTokenProvider(redis_client)
    tool_executor = GraphToolExecutor(HttpxGraphMailClient())
    return SendChatMessageUseCase(
        _get_chat_client(), conversation_repository, token_provider, tool_executor
    )


def get_conversation_repository(session: SessionDep) -> SqlAlchemyConversationRepository:
    return SqlAlchemyConversationRepository(session, redis_client)


def get_create_calendar_event_use_case() -> CreateCalendarEventUseCase:
    token_provider = MsalOboTokenProvider(redis_client)
    calendar_client = HttpxGraphCalendarClient()
    return CreateCalendarEventUseCase(token_provider, calendar_client)
