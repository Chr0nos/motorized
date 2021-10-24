from functools import wraps
from contextlib import asynccontextmanager

from motorized import connection


@asynccontextmanager
async def database(drop_before=True, drop_after=True):
    db_name = 'dontuse'
    await connection.connect(f'mongodb://192.168.1.12:27017/{db_name}')
    if drop_before:
        await connection.client.drop_database(db_name)
    yield connection.database
    if drop_after:
        await connection.client.drop_database(db_name)
    await connection.disconnect()


def require_db(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with database(drop_after=False):
            return await func(*args, **kwargs)
    return wrapper
