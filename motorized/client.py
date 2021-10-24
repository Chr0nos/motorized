from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from contextlib import asynccontextmanager


class Connection:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None

    async def connect(self, *args, **kwargs):
        print(f'Connection to {args} {kwargs}')
        self.client = AsyncIOMotorClient(*args, **kwargs)
        self.database = self.client.get_default_database()

    async def disconnect(self) -> None:
        self.client = None
        self.database = None


@asynccontextmanager
async def use_client(
    *args,
    client: Optional[AsyncIOMotorClient] = None,
    **kwargs
):
    if not client:
        client = AsyncIOMotorClient(*args, **kwargs)
    old_client = connection.client
    old_database = connection.database
    connection.client = client
    connection.database = client.get_default_database()
    yield
    connection.client = old_client
    connection.database = old_database


connection = Connection()
