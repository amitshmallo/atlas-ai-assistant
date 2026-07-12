from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces import HealthCheckRepository


class SqlAlchemyHealthCheckRepository(HealthCheckRepository):
    """Concrete implementation of the domain HealthCheckRepository interface,
    backed by a real database connection."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_database(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
