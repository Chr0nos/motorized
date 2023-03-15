import asyncio

from motorized.migration import list_migrations
from depsolve import walk


async def migrate(*folders) -> None:
    """Newer version of migrate for python3.11 using TaskGroup
    need more testing
    """
    migrations = []
    tasks = []
    async with asyncio.TaskGroup() as tg:
        for folder in folders:
            tasks.append(tg.create_task(list_migrations(folder)))

    migrations = [task.result() for task in tasks]

    async with asyncio.TaskGroup() as tg:
        for migration in walk(migrations):
            tg.create_task(migration.apply())
