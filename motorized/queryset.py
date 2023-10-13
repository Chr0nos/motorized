from abc import ABC
from typing import (
    Any,
    Generator,
    List,
    Callable,
    Dict,
    Optional,
    AsyncGenerator,
    Type,
    TypeVar,
    Generic,
    Self,
)
from motor.motor_asyncio import (
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
    AsyncIOMotorCursor,
    AsyncIOMotorClientSession,
)
from pymongo import ASCENDING, DESCENDING
from pymongo.results import InsertOneResult, UpdateResult
from motorized.query import Q, QueryDict
from motorized.client import connection
from motorized.exceptions import NotConnectedException
from contextlib import contextmanager


T = TypeVar("T")


class QuerySet(Generic[T], ABC):
    def __init__(self, model: Type[T], initial_query: Q | None = None):
        self.model: Type[T] = model
        self._query: Q = initial_query or Q()
        self._initial_query: Q | None = initial_query
        self._limit: int | None = None
        self._skip: int | None = None
        self._sort: list[tuple[str, int]] | None = None
        self.database: AsyncIOMotorDatabase | None = None
        self._session: AsyncIOMotorClientSession | None = None
        # _collection_name allow you to override used collection name,
        # priority order is: _collection_name > Document.Mongo.collection
        self._collection_name: Optional[str] = None

    def copy(self) -> Self:
        instance = self.__class__(self.model)
        instance._query = self._query.copy()
        instance._limit = self._limit
        instance._sort = self._sort
        instance._skip = self._skip
        instance._collection_name = self._collection_name
        instance.use_database(self.database)
        return instance

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.model.__name__}: " f"{self._query}>"

    @classmethod
    def from_query(cls, model: T, query: Q) -> Self:
        instance = QuerySet(model)
        instance._query = query
        return instance

    def use_database(self, database: AsyncIOMotorDatabase | None) -> None:
        """if `database` is None then the default database will be used."""
        self.database = database

    def use_session(self, session: AsyncIOMotorClientSession) -> Self:
        instance = self.copy()
        instance._session = session
        return instance

    @contextmanager
    def collection_name(self, collection_name: str) -> Generator[None, None, Self]:
        """Allow the user to override the destination collection,
        use this context manager to copy items from one collection to an other.
        usage:
        ```python
        item = await Document.objects.first()
        with Document.objects.collection_name("migration"):
            await item.save()
        ```
        """
        original_collection_name = self._collection_name
        self._collection_name = collection_name
        yield self
        self._collection_name = original_collection_name

    async def __aiter__(self) -> AsyncGenerator[T, None]:
        cursor = await self.find()
        async for data in cursor:
            instance = self.model(**data)
            yield instance

    async def create(self, *args, **kwargs) -> T:
        instance = self.model(*args, **kwargs)
        await instance.save()
        return instance

    async def insert_one(self, data: dict, **kwargs) -> InsertOneResult:
        kwargs.setdefault("session", self._session)
        return await self.collection.insert_one(data, **kwargs)

    @property
    def collection(self) -> AsyncIOMotorCollection:
        collection_name: str = self._collection_name or self.model.Mongo.collection
        if self.database is not None:
            return getattr(self.database, collection_name)
        if connection.database is None:
            raise NotConnectedException(
                "You need to use connection.connect before using collection"
            )
        return getattr(connection.database, collection_name)

    async def count(self, **kwargs) -> int:
        return await self.collection.count_documents(self._query.query, **kwargs)

    async def first(self) -> T | None:
        raw_data = await self.find_one()
        if raw_data is None:
            return None
        instance = self.model(**raw_data)
        return instance

    async def drop(self) -> None:
        await self.collection.drop()

    def filter(self, query: Q | None = None, /, **kwargs) -> Self:
        instance = self.copy()
        if query:
            instance._query += query
        instance._query += Q(**kwargs)
        return instance

    def exclude(self, **kwargs) -> Self:
        instance = self.copy()
        inner_query = Q()
        inner_query.query = Q.convert_kwargs_to_query(**kwargs, invert=True)
        instance._query += inner_query
        return instance

    def limit(self, size: int | None) -> Self:
        """Limit the result of the query to the specified size,
        passing a `None` as size will remove any limitations
        """
        if size is not None and size < 0:
            raise ValueError(size)
        instance = self.copy()
        instance._limit = size
        return instance

    def skip(self, offset: int | None = None) -> Self:
        """Request an offset from the database to the results, if you pass a
        `None` as offset then no offset will be applied
        """
        if offset is not None and offset < 0:
            raise ValueError(offset)
        instance = self.copy()
        instance._skip = offset
        return instance

    def order_by(self, ordering: str | list[str] | None) -> Self:
        instance = self.copy()
        if ordering:
            instance._sort = self._sort_instruction(
                ordering if hasattr(ordering, "__iter__") else [ordering]
            )
        else:
            instance._sort = None
        return instance

    def __add__(self, other: Self) -> Self:
        instance = self.copy()
        instance._query += other._query
        return instance

    async def all(self) -> list[T]:
        return list([instance async for instance in self])

    async def map(self, func: Callable) -> List[Any]:
        """Apply `func` to all match in the query queryset and return the
        result of the function in a list.
        """
        return list([await func(instance) async for instance in self])

    async def distinct(self, key: str, **kwargs) -> List[Any]:
        if not self._query.is_empty():
            kwargs.setdefault("filter", self._query.query)
        return await self.collection.distinct(key, **kwargs)

    async def aggregate(self, pipeline, **kwargs) -> Any:
        kwargs.setdefault("session", self._session)
        return await self.collection.aggregate(pipeline, **kwargs)

    async def find(self, **kwargs) -> AsyncIOMotorCursor:
        kwargs.setdefault("session", self._session)
        cursor = self.collection.find(self._query.query, **kwargs)
        return await self._paginate_cursor(cursor)

    async def find_one(self, **kwargs) -> Dict:
        kwargs.setdefault("session", self._session)
        return await self.collection.find_one(filter=self._query.query, sort=self._sort, **kwargs)

    async def get(self, **kwargs) -> T:
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

    def fresh(self) -> Self:
        """Return a fresh queryset without any filtering/ordering/limiting
        parameter as fresh as new.
        """
        instance = QuerySet(self.model, self._initial_query)
        instance.use_database(self.database)
        return instance

    async def values_list(self, fields: list[str], flat=False, noid=False):
        if isinstance(fields, str):
            fields = (fields,)
        projection = {f: True for f in fields}
        if noid:
            projection["_id"] = False

        cursor: AsyncIOMotorCursor = await self.find(projection=projection)
        if not flat:
            return list([item async for item in cursor])
        assert len(fields) == 1, "You can only have one field using flat=True"
        field_name = fields[0]
        return list([value[field_name] async for value in cursor])

    async def _paginate_cursor(self, cursor: AsyncIOMotorCursor) -> AsyncIOMotorCursor:
        if self._sort:
            cursor = cursor.sort(self._sort)
        if self._limit:
            cursor = cursor.limit(self._limit)
        if self._skip:
            cursor = cursor.skip(self._skip)
        return cursor

    @staticmethod
    def _sort_instruction(order: list[str]) -> list[tuple[str, int]]:
        """Convert a list for format:
        ['name', '-age'] to:
        [('name': 1), ('age': -1)]
        """

        def generate_tuple(word) -> tuple[str, int]:
            if word.startswith("-"):
                return (word[1:], DESCENDING)
            return (word, ASCENDING)

        return [generate_tuple(word) for word in order]

    async def exists(self) -> bool:
        return await self.collection.count_documents(self._query.query, limit=1) > 0

    async def delete(self, **kwargs):
        kwargs.setdefault("session", self._session)
        return await self.collection.delete_many(self._query.query, **kwargs)

    async def delete_one(self, **kwargs):
        kwargs.setdefault("session", self._session)
        return await self.collection.delete_one(self._query.query, **kwargs)

    async def pop(self, session: AsyncIOMotorClientSession | None = None, **kwargs) -> T:
        """Retrieve a document and delete it from the database."""
        instance = self.filter(**kwargs)
        document_dict = await instance.collection.find_one_and_delete(
            instance.query._query, session=session or self._session
        )
        document = self.model(**document_dict)
        return document

    async def indexes(self):
        return [index async for index in self.collection.list_indexes()]

    def _get_paginated_pipeline_basis(self) -> list[dict]:
        """Construct a List[Dict] with the pagination information for the
        pipeline (ordering/limit/offset)
        if no pagination information are present in the QuerySet an empty
        list will be returned.
        """
        pipeline = []
        if self._sort:
            pipeline.append({"$sort": {field_name: order for field_name, order in self._sort}})
        if self._limit:
            pipeline.append({"$limit": self._limit + (self._skip or 0)})
        if self._skip:
            pipeline.append({"$skip": self._skip})
        return pipeline

    async def _aggregate(self, operator: str, fields: str | list[str], **kwargs) -> int | dict:
        """Create a mongodb pipeline on all given `fields` using the operator
        (ex: $sum) if the `fields` parameter is a List then a dictionary of the
        values will be returned, the keys will be the fields names,
        if the `fields` parameter is an instance of string then the value will
        be directly returned.
        """
        kwargs.setdefault("session", self._session)
        if isinstance(fields, str):
            fields = [fields]
        pipeline = self._get_paginated_pipeline_basis()
        pipeline.extend(
            [
                {"$match": self._query.query},
                {
                    "$group": {
                        "_id": "total",
                        **{field: {operator: f"${field}"} for field in fields},
                    }
                },
            ]
        )

        cursor = self.collection.aggregate(pipeline, **kwargs)
        result = await cursor.next()
        # if the list only has one element we just return the first result
        if len(fields) == 1:
            return result[fields[0]]
        result.pop("_id", None)
        return result

    async def sum(self, fields: str | list[str]) -> int | dict:
        return await self._aggregate("$sum", fields)

    async def avg(self, fields: str | list[str]) -> float | dict:
        """Return the average for the given field or list of fields,
        if the fields is only one string the result will be the number directly
        otherwise it will be a dictionary with fields names as keys and
        averages as values
        """
        return await self._aggregate("$avg", fields)

    async def update(self, **kwargs) -> UpdateResult:
        """Perform an update on the current queryset, matching documents will
        be updated according to the parameters
        ex:
        ```python
        User.objects.filter(is_admin).update(is_admin=False)
        ```

        Note this function WILL NOT PERFORM ANY VALIDATION on the input data
        it's up to you, be carefull and validate it before.
        """
        updater = QueryDict(**kwargs)
        return await self.collection.update_many(
            self._query.query, {"$set": updater}, session=self._session
        )

    async def unset(self, fields_names: list[str]) -> UpdateResult:
        """Remove fields from documents
        example:
        ```python
        await Book.objects.filter(some_field__exists=True).unset(['some_field'])
        ```
        Note this could break the validation of the ODM and lead to data not
        being consitent anymore, use it carefully
        """
        fields = list([".".join(item.split("__")) for item in fields_names])
        fields_dict = {field: "" for field in fields}
        return await self.collection.update_many(
            self._query.query, {"$unset": fields_dict}, session=self._session
        )

    async def rename(self, fields: dict[str, str]) -> int:
        """Renames fields from key to values."""
        return (
            await self.collection.update_many(self._query.query, {"$rename": fields})
        ).modified_count
