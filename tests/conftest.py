import pytest_asyncio

from app.infrastructure.database import engine


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_after_test():
    """pytest-asyncio gives each test function its own event loop, but
    app.infrastructure.database's engine (and its connection pool) is a
    module-level singleton created once. On Windows, reusing a pool whose
    connections were opened under a now-closed ProactorEventLoop raises
    'Event loop is closed' during teardown of the *next* test. Disposing
    the pool after every test forces fresh connections under whichever
    loop is current, at the cost of a bit of per-test connection overhead
    — the production app doesn't have this problem since it runs one
    long-lived event loop under uvicorn, not one per test."""
    yield
    await engine.dispose()
