import pytest

from motorized.client import client, connection


@pytest.mark.asyncio
async def test_client_context_manager(database_uri: str):
    async with client(database_uri):
        assert connection.database is not None
        assert connection.client
    assert not connection.database
    assert not connection.client
