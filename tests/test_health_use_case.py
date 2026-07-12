from app.application.health import GetHealthStatusUseCase


class FakeHealthCheckRepository:
    """A test double for the domain.HealthCheckRepository interface —
    no database, no infrastructure import required."""

    def __init__(self, database_ok: bool) -> None:
        self._database_ok = database_ok

    async def check_database(self) -> bool:
        return self._database_ok


async def test_health_status_is_healthy_when_database_is_up():
    use_case = GetHealthStatusUseCase(FakeHealthCheckRepository(database_ok=True))

    status = await use_case.execute()

    assert status.api is True
    assert status.database is True
    assert status.healthy is True


async def test_health_status_is_unhealthy_when_database_is_down():
    use_case = GetHealthStatusUseCase(FakeHealthCheckRepository(database_ok=False))

    status = await use_case.execute()

    assert status.database is False
    assert status.healthy is False
