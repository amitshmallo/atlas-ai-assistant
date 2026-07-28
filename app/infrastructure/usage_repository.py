from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TokenUsage
from app.infrastructure.usage_models import UsageRecordModel


class SqlAlchemyUsageRepository:
    """Concrete implementation of domain.UsageRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_usage(self, user_oid: str, usage: TokenUsage) -> None:
        self._session.add(
            UsageRecordModel(
                user_oid=user_oid,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
        )
        await self._session.commit()

    async def get_summary(self, user_oid: str, since_days: int) -> tuple[int, int, int]:
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
        result = await self._session.execute(
            select(
                func.coalesce(func.sum(UsageRecordModel.prompt_tokens), 0),
                func.coalesce(func.sum(UsageRecordModel.completion_tokens), 0),
                func.count(UsageRecordModel.id),
            ).where(UsageRecordModel.user_oid == user_oid, UsageRecordModel.created_at >= since)
        )
        prompt_tokens, completion_tokens, turn_count = result.one()
        return int(prompt_tokens), int(completion_tokens), int(turn_count)
