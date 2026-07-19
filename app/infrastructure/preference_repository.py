from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import UserPreference
from app.infrastructure.preference_models import PreferenceModel


class SqlAlchemyPreferenceRepository:
    """Concrete implementation of domain.PreferenceRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_preferences(self, user_oid: str) -> list[UserPreference]:
        result = await self._session.execute(
            select(PreferenceModel).where(PreferenceModel.user_oid == user_oid)
        )
        return [UserPreference(key=row.key, value=row.value) for row in result.scalars().all()]

    async def set_preference(self, user_oid: str, key: str, value: str) -> None:
        statement = insert(PreferenceModel).values(user_oid=user_oid, key=key, value=value)
        statement = statement.on_conflict_do_update(
            constraint="uq_preferences_user_oid_key",
            set_={"value": statement.excluded.value},
        )
        await self._session.execute(statement)
        await self._session.commit()
