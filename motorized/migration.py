import os
from glob import glob
from typing import Literal, Callable, Any, Optional, Dict, Type
from datetime import datetime
from importlib import import_module
from motorized import Document
import logging
import asyncio
from depsolve import walk


"""
# Migrations
each migration is supposed be a file in a folder (of your choice),
each file nameing should be: YYYYMMDDXX
when:
YYYY = year on 4 chars
MM = month on 2 chars
DD = day on 2 chars
XX = migration of the day from 00 to 99 (on 2 chars)

all migrations will be evaluated and applied in a lexical order.

each migration should contain at last:
- async apply function to perform the migration
- async revert function to revert it if possible

it's also a good practice to provide a `description` variable on the top scope
of your migration module to let co-workers know what it is intended for.

example migration of a file "2021021400.py":
```python
from motorized.migration import alter_field
from my_models import User

description = 'convert User.age from string to integer'


async def apply() -> int:
    return alter_field(User, 'age', lambda age: int(age)})


async def revert() -> int:
    return alter_field(User, 'age', lambda age: str(age))
```
"""


logger = logging.getLogger(__name__)

# thoses are the types from
# https://docs.mongodb.com/manual/reference/bson-types/
MongoType = Literal[
    "double",
    "string",
    "object",
    "array",
    "binData" "undefined",
    "objectId",
    "bool",
    "date",
    "null",
    "regex",
    "dbPointer",
    "javascript",
    "symbol",
    "javascriptWithScope",
    "int",
    "timestamp",
    "long",
    "decimal",
    "minKey",
    "maxKey",
    "binData",
]


class Migration(Document):
    module_name: str
    applied_at: Optional[datetime] = None
    depends_on = []

    class Mongo:
        local_fields = ("depends_on",)

    @property
    def name(self) -> str:
        return self.module_name

    def __str__(self):
        return self.module_name

    async def is_applied(self) -> bool:
        if self.id and self.applied_at:
            return True
        return await Migration.objects.filter(module_name=self.module_name).exists()

    @property
    def path(self) -> str:
        return self.module_name.replace(".", "/") + ".py"

    @property
    def exists(self) -> bool:
        return os.path.exists(self.path)

    async def save(self, *args, **kwargs):
        if not self.applied_at:
            self.applied_at = datetime.utcnow()
        return await super().save(*args, **kwargs)

    async def apply(self, force: bool = False) -> int:
        """Apply the migration to the database and save the instance into
        the collection.
        `force` param allow you to force application of the migration even if
        it was already applied.
        if the migration has already been applied then 0 will be returned
        and a warning displayed
        return the amount of modified rows in the collection
        """
        if await self.is_applied() and not force:
            logger.info(f"{self.module_name} already applied.")
            return 0

        migration_module = import_module(self.module_name)
        if not hasattr(migration_module, "apply"):
            logger.error(f"{self} is malformed: no `apply` method found.")
            raise ValueError(self)

        # description formating if available
        description = getattr(migration_module, "description", None)
        description: str = ": " + description if description else "."

        # perform the actual migration
        modified_count = await migration_module.apply()
        logger.info(f"Applied {self.module_name} on {modified_count} rows{description}")
        await self.save()
        return modified_count

    async def revert(self) -> int:
        if not await self.is_applied():
            logger.warning(f"Cannot revert {self.module_name} since it wasent applied")
            return 0
        migration_module = import_module(self.module_name)
        try:
            modified_count = await migration_module.revert()
            print("revert function ok", modified_count)
            logger.info(f"Reverted {self.module_name} on {modified_count} rows.")
            await self.delete()
            return modified_count
        except AttributeError as error:
            logger.error("Migration {self.module_name} cannot be undone.")
            raise ValueError(f"{self} cannot be undone.") from error

    def __eq__(self, other: "Migration") -> bool:
        return self.module_name == other.module_name

    @classmethod
    def from_module(cls, module: str) -> "Migration":
        migration_module = import_module(module)
        if not hasattr(migration_module, "apply"):
            raise ValueError(f"Module {module} does not have a apply function")
        migration = cls(
            module_name=module,
            depends_on=getattr(migration_module, "depends_on", []),
            applied_at=None,
        )
        return migration


def value_from_dot_notation(data: Dict[str, Any], path: str) -> Any:
    """Take a dictionary `data` and get keys by the `path` parameter,
    this path parameter will use the dots (.) as delimiter.
    """
    for key in path.split("."):
        data = data[key]
    return data


async def alter_field(
    model: Type[Document],
    field_name: str,
    caster: Callable[[Any], Any],
    filter: Optional[Dict[str, Any]] = None,
) -> int:
    """Alter the `field_name` on `model` using the `caster` function,
    the function will receive the value to convert as parameter.

    the alteration will be done row by row instead of a collection.update_many
    to allow custom conversions (cast/setting default values etc).
    """
    if filter is None:
        filter = {}
    projection = {field_name: True, "_id": True}
    cursor = model.collection.find(filter, projection)
    modified_count = 0
    async for item in cursor:
        casted = await caster(value_from_dot_notation(item, field_name))
        await model.collection.update_one({"_id": item["_id"]}, {"$set": {field_name: casted}})
        modified_count += 1
    return modified_count


async def list_migrations(folder: str) -> list[Migration]:
    migrations = []
    for item in glob(folder + "/*.py"):
        if not os.path.isfile(item):
            continue
        module_name = item.replace("/", ".").replace(".py", "")
        try:
            migrations.append(Migration.from_module(module_name))
        except ValueError:
            continue
    return migrations


async def migrate(*folders: str) -> None:
    migrations = []
    for folder in folders:
        migrations.extend(await list_migrations(folder))

    for migrations in walk(migrations):
        tasks = list([migration.apply() for migration in migrations])
        await asyncio.gather(*tasks)
