import os
from glob import glob
from typing import List, Literal, Callable, Any, Optional, Dict, Type
from datetime import datetime
from importlib import import_module
from motorized import Document, QuerySet
import logging

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
logger.setLevel(logging.DEBUG)

# thoses are the types from
# https://docs.mongodb.com/manual/reference/bson-types/
MongoType = Literal[
    "double",
    "string",
    "object",
    "array",
    "binData"
    "undefined",
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


class MigrationManager(QuerySet):
    def discover(self, folder: str) -> List[str]:
        return list(sorted([
            os.path.basename(filename).replace('/', '.').replace('.py', '')
            for filename in glob(folder + '/*.py')
            if os.path.isfile(filename)
        ]))

    async def pending(self, folder: str) -> List["Migration"]:
        return list([
            self.model(module_name=module_name)
            for module_name in self.discover(folder)
            if not await self.filter(module_name=module_name).exists()
        ])

    async def migrate(self, folder: str) -> int:
        modified_count = 0
        for migration in await self.pending(folder):
            modified_count += await migration.apply()
        return modified_count


class Migration(Document):
    module_name: str
    applied_at: Optional[datetime] = None

    class Mongo:
        manager_class = MigrationManager

    @property
    def is_applied(self) -> bool:
        return self.id is not None and self.applied_at is not None

    async def save(self, *args, **kwargs):
        self.applied_at = datetime.utcnow()
        return await super().save(*args, **kwargs)

    async def apply(self) -> int:
        if self.is_applied:
            logger.warning("{self.module_name} already applied.")
            return 0
        migration_module = import_module(self.module_name)
        description = getattr(migration_module, 'description', None)
        if description is not None:
            description = ': ' + description
        else:
            description = '.'
        modified_count = await migration_module.apply()
        logger.info(f"Applied {self.module_name} on {modified_count} rows{description}")
        await self.save()
        return modified_count

    async def revert(self) -> int:
        if not self.is_applied:
            logger.warning(f"Cannot revert {self.module_name} since it wasent applied")
            return 0
        migration_module = import_module(self.module_name)
        try:
            modified_count = await migration_module.revert()
            print('revert function ok', modified_count)
            logger.info(f"Reverted {self.module_name} on {modified_count} rows.")
            await self.delete()
            return modified_count
        except AttributeError as error:
            logger.error("Migration {self.module_name} cannot be undone.")
            raise ValueError(f"{self} cannot be undone.") from error

    def __eq__(self, other: "Migration") -> bool:
        return self.module_name == other.module_name


def value_from_dot_notation(data: Dict[str, Any], path: str) -> Any:
    for key in path.split('.'):
        data = data[key]
    return data


async def alter_field(
    model: Type[Document],
    field_name: str,
    caster: Callable[[Any], Any],
    filter: Optional[Dict[str, Any]] = None,
) -> int:
    if filter is None:
        filter = {}
    projection = {field_name: True, '_id': True}
    cursor = model.collection.find(filter, projection)
    modified_count = 0
    async for item in cursor:
        casted = await caster(value_from_dot_notation(item, field_name))
        await model.collection.update_one(
            item['_id'],
            {'$set': {field_name: casted}}
        )
        modified_count += 1
    return modified_count
