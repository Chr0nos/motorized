import os
from glob import glob
from typing import List, Literal, Callable, Any, Optional, Dict, Type
from datetime import datetime
from importlib import import_module
from motorized import Document, QuerySet
import logging


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
    def applied(self) -> bool:
        return self.id is not None and self.applied_at is not None

    async def save(self, *args, **kwargs):
        self.applied_at = datetime.utcnow()
        return await super().save(*args, **kwargs)

    async def apply(self) -> int:
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
        if not self.applied:
            logger.error(f"Cannot revert {self.module_name} since it wasent applied")
            raise ValueError("Cannot revert this migration since it wasent applied.")
        migration_module = import_module(self.module_name)
        modified_count = await migration_module.revert()
        logger.info(f"Reverted {self.module_name} on {modified_count} rows.")
        await self.delete()
        return modified_count

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
