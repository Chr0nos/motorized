from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from contextlib import asynccontextmanager


class Connection:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None

    async def connect(self, *args, **kwargs):
        self.client = AsyncIOMotorClient(*args, **kwargs)
        self.database = self.client.get_default_database()

    async def disconnect(self) -> None:
        self.client = None
        self.database = None

    def set_database(self, name: str, **kwargs) -> None:
        """Set the current database to use
        after using the default database for authentication
        then you set the product database with this method.
        """
        self.database = AsyncIOMotorDatabase(client=self.client, name=name, **kwargs)


@asynccontextmanager
async def client(*args, client: AsyncIOMotorClient | None = None, **kwargs):
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
