"""Integration test against the real Postgres container (docker compose)
— proves the ON CONFLICT upsert actually works, not just that the SQL
statement is well-formed. Uses a random user_oid per test to avoid
collisions with other test runs / manual testing data."""

import uuid

from app.infrastructure.database import async_session_factory
from app.infrastructure.preference_repository import SqlAlchemyPreferenceRepository


async def test_set_preference_then_get_preferences_round_trips():
    user_oid = f"test-user-{uuid.uuid4()}"

    async with async_session_factory() as session:
        repository = SqlAlchemyPreferenceRepository(session)
        await repository.set_preference(user_oid, "reply_style", "concise")

        preferences = await repository.get_preferences(user_oid)

    assert len(preferences) == 1
    assert preferences[0].key == "reply_style"
    assert preferences[0].value == "concise"


async def test_set_preference_upserts_existing_key():
    user_oid = f"test-user-{uuid.uuid4()}"

    async with async_session_factory() as session:
        repository = SqlAlchemyPreferenceRepository(session)
        await repository.set_preference(user_oid, "reply_style", "concise")
        await repository.set_preference(user_oid, "reply_style", "detailed")

        preferences = await repository.get_preferences(user_oid)

    assert len(preferences) == 1
    assert preferences[0].value == "detailed"


async def test_preferences_are_isolated_per_user():
    user_a = f"test-user-{uuid.uuid4()}"
    user_b = f"test-user-{uuid.uuid4()}"

    async with async_session_factory() as session:
        repository = SqlAlchemyPreferenceRepository(session)
        await repository.set_preference(user_a, "reply_style", "concise")

        preferences_for_b = await repository.get_preferences(user_b)

    assert preferences_for_b == []
