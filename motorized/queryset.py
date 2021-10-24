from typing import (
    Any, List, Callable, Dict, Optional, AsyncGenerator, Tuple, Union, Type
)
from motor.motor_asyncio import (
    AsyncIOMotorCollection, AsyncIOMotorDatabase, AsyncIOMotorCursor
)

from motorized.query import Q
from motorized.client import connection
from motorized.exceptions import NotConnectedException


class QuerySet:
    def __init__(self, model, initial_query: Optional[Q] = None):
        self.model = model
        self._query = initial_query or Q()
        self._initial_query: Optional[Q] = initial_query
        self._limit = None
        self._sort = None
        self.database = None

    def copy(self) -> "QuerySet":
        instance = self.__class__(self.model)
        instance._query = self._query.copy()
        instance._limit = self._limit
        instance._sort = self._sort
        instance.use(self.database)
        return instance

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self.model.__name__}: ' \
               f'{self._query}>'

    @classmethod
    def from_query(cls,
                   model: Type["Document"],  # noqa: F821
                   query: Q) -> "QuerySet":
        instance = QuerySet(model)
        instance._query = query
        return instance

    def use(self, database: Optional[AsyncIOMotorDatabase]) -> None:
        """if `database` is None then the default database will be used.
        """
        self.database = database

    async def __aiter__(self) -> AsyncGenerator["Document", None]:  # noqa: F821,E501
        cursor = await self.find()
        async for data in cursor:
            instance = self.model(**data)
            yield instance

    async def create(self, *args, **kwargs) -> "Document":  # noqa: F821
        instance = self.model(*args, **kwargs)
        await instance.save()
        return instance

    @property
    def collection(self) -> AsyncIOMotorCollection:
        if self.database is not None:
            return getattr(self.database, self.model.Mongo.collection)
        if not connection.database:
            raise NotConnectedException(
                'You need to use connection.connect before using collection'
            )
        return getattr(connection.database, self.model.Mongo.collection)

    async def count(self, **kwargs) -> int:
        return await self.collection.count_documents(
            self._query.query, **kwargs)

    async def first(self) -> Optional["Document"]:  # noqa: F821
        raw_data = await self.find_one()
        if raw_data is None:
            return None
        instance = self.model(**raw_data)
        return instance

    async def drop(self) -> None:
        await self.collection.drop()

    def filter(self, query: Optional[Q] = None, /, **kwargs) -> "QuerySet":
        instance = self.copy()
        if query:
            instance._query += query
        instance._query += Q(**kwargs)
        return instance

    def exclude(self, **kwargs) -> "QuerySet":
        instance = self.copy()
        inner_query = Q()
        inner_query.query = Q.convert_kwargs_to_query(**kwargs, invert=True)
        instance._query += inner_query
        return instance

    def limit(self, size: int) -> "QuerySet":
        instance = self.copy()
        instance._limit = size
        return instance

    def order_by(
        self,
        ordering: Optional[Union[str, List[str]]]
    ) -> "QuerySet":
        instance = self.copy()
        if ordering:
            instance._sort = self._sort_instruction(
                ordering if hasattr(ordering, '__iter__') else [ordering]
            )
        else:
            instance._sort = None
        return instance

    def __add__(self, other: "QuerySet") -> "QuerySet":
        instance = self.copy()
        instance._query += other._query
        return instance

    async def all(self) -> List["Document"]:  # noqa: F821
        return [instance async for instance in self]

    async def map(self, func: Callable) -> List[Any]:
        """Apply `func` to all match in the query queryset and return the
        result of the function in a list.
        """
        return list([await func(instance) async for instance in self])

    async def distinct(self, key: str, **kwargs) -> List[Any]:
        if not self._query.is_empty():
            kwargs.setdefault('filter', self._query.query)
        return await self.collection.distinct(key, **kwargs)

    async def aggregate(self, pipeline, **kwargs) -> Any:
        return await self.collection.aggregate(pipeline, **kwargs)

    async def find(self, **kwargs) -> AsyncIOMotorCursor:
        cursor = self.collection.find(self._query.query, **kwargs)
        return await self._paginate_cursor(cursor)

    async def find_one(self) -> Dict:
        return await self.collection.find_one(self._query.query)

    async def get(self, **kwargs) -> "Document":  # noqa: F821
        instance = self.filter(**kwargs)
        cursor = await instance.find()
        try:
            first = await cursor.__anext__()
        except StopAsyncIteration as error:
            raise self.model.DocumentNotFound(self._query.query) from error
        try:
            await cursor.__anext__()
        except StopAsyncIteration:
            return self.model(**first)

        raise self.model.TooManyMatchException

    def fresh(self) -> "QuerySet":
        """Return a fresh queryset without any filtering/ordering/limiting
        parameter as fresh as new.
        """
        instance = QuerySet(self.model, self._initial_query)
        instance.use(self.database)
        return instance

    async def values_list(self, fields: List[str], flat=False, noid=False):
        if isinstance(fields, str):
            fields = (fields,)
        projection = {f: True for f in fields}
        if noid:
            projection['_id'] = False

        cursor: AsyncIOMotorCursor = await self.find(projection=projection)
        if not flat:
            return list([item async for item in cursor])
        assert len(fields) == 1, 'You can only have one field using flat=True'
        field_name = fields[0]
        return list([value[field_name] async for value in cursor])

    async def _paginate_cursor(
        self,
        cursor: AsyncIOMotorCursor
    ) -> AsyncIOMotorCursor:
        if self._sort:
            cursor = cursor.sort(self._sort)
        if self._limit:
            cursor = cursor.limit(self._limit)
        return cursor

    @staticmethod
    def _sort_instruction(order: List[str]) -> List[Tuple[str, int]]:
        """Convert a list for format:
        ['name', '-age'] to:
        [('name': 1), ('age': -1)]
        """
        def generate_tuple(word) -> Tuple[str, int]:
            if word.startswith('-'):
                return (word[1:], -1)
            return (word, 1)

        return [generate_tuple(word) for word in order]

    async def exists(self) -> bool:
        return await self.collection.count_documents(
            self._query.query, limit=1) > 0

    async def delete(self, **kwargs):
        return await self.collection.delete_many(self._query.query, **kwargs)

    async def delete_one(self, **kwargs):
        return await self.collection.delete_one(self._query.query, **kwargs)

    async def pop(self, **kwargs) -> "Document":  # noqa: F821
        instance = self.filter(**kwargs)
        document_dict = await instance.collection.find_one_and_delete(
            instance.query._query
        )
        document = self.model(**document_dict)
        return document

    async def indexes(self):
        return [index async for index in self.collection.list_indexes()]

    async def _aggregate(
        self,
        operator: str,
        fields: Union[str, List[str]]
    ) -> Union[int, Dict]:
        """Create a mongodb pipeline on all given `fields` using the operator
        (ex: $sum) if the `fields` parameter is a List then a dictionary of the
        values will be returned, the keys will be the fields names,
        if the `fields` parameter is an instance of string then the value will
        be directly returned.
        """
        if isinstance(fields, str):
            fields = [fields]
        pipeline = [
            {"$match": self._query.query},
            {
                "$group": {
                    "_id": "total",
                    **{field: {operator: f'${field}'} for field in fields}
                }
            }
        ]
        cursor = self.collection.aggregate(pipeline)
        result = await cursor.next()
        # if the list only has one element we just return the first result
        if len(fields) == 1:
            return result[fields[0]]
        result.pop('_id', None)
        return result

    async def sum(self, fields: Union[str, List[str]]) -> Union[int, Dict]:
        return await self._aggregate('$sum', fields)

    async def avg(self, fields: Union[str, List[str]]) -> Union[float, Dict]:
        return await self._aggregate('$avg', fields)
