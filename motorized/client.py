
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


class Connection:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None

    async def connect(self, *args, **kwargs):
        print(f'Conncetion to {args} {kwargs}')
        self.client = AsyncIOMotorClient(*args, **kwargs)
        self.database = self.client.get_default_database()

    async def disconnect(self) -> None:
        self.client = None
        self.database = None


connection = Connection()
