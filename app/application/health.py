from app.domain.entities import HealthStatus
from app.domain.interfaces import HealthCheckRepository


class GetHealthStatusUseCase:
    """Depends only on the HealthCheckRepository interface, not on any
    concrete infrastructure — this is the dependency-inversion boundary."""

    def __init__(self, health_repository: HealthCheckRepository) -> None:
        self._health_repository = health_repository

    async def execute(self) -> HealthStatus:
        database_ok = await self._health_repository.check_database()
        return HealthStatus(api=True, database=database_ok)
