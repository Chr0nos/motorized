from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from typing import Optional, Union, Any, Optional, Dict, Type
from pydantic import BaseModel, Field
from pydantic.main import ModelMetaclass
from pymongo.results import InsertOneResult, UpdateResult

from motorized.queryset import QuerySet
from motorized.query import Q
from motorized.types import PydanticObjectId, ObjectId
from motorized.exceptions import DocumentNotSavedError


class DocumentMeta(ModelMetaclass):
    def __new__(cls, name, bases, optdict: Dict) -> Type['DocumentBase']:
        instance: Type[DocumentBase] = super().__new__(cls, name, bases, optdict)
        manager_class = getattr(instance.Mongo, 'manager_class', QuerySet)
        instance.objects = manager_class(instance)
        # print(name, instance.Mongo.collection)
        if instance.Mongo.collection is None and name not in ('Document', 'DocumentBase'):
            instance.Mongo.collection = name.lower() + 's'

        class DocumentError(Exception):
            pass

        class TooManyMatchException(DocumentError):
            pass

        class DocumentNotFound(DocumentError):
            pass

        instance.DocumentError = DocumentError
        instance.TooManyMatchException = TooManyMatchException
        instance.DocumentNotFound = DocumentNotFound
        return instance


class DocumentBase(metaclass=DocumentMeta):
    class Mongo:
        manager_class = QuerySet
        collection = None

    def get_query(self) -> Q:
        document_id = getattr(self, 'id', None)
        if not document_id:
            raise DocumentNotSavedError('document has no id.')
        return Q(_id=document_id)

    async def _create(self, creation_dict: Dict) -> InsertOneResult:
        response = await self.objects.collection.insert_one(creation_dict)
        self.id = response.inserted_id
        return response

    async def save(self) -> Union[InsertOneResult, UpdateResult]:
        data = self.dict()
        document_id = data.pop('id', None)
        if document_id is None:
            return await self._create(data)
        return await self.objects.collection.update_one(
            filter={'_id': document_id},
            update={'$set': data}
        )

    async def commit(self) -> "Document":
        """Same as `.save` but return the current instance.
        """
        await self.save()
        return self

    async def delete(self) -> "Document":
        """Delete the current instance from the database,
        to the deleted the instance need to have a .id set, in any case the function
        will return the instance itself
        """
        try:
            qs = self.objects.from_query(self, self.get_query())
            await qs.delete_one()
        except DocumentNotSavedError:
            pass
        setattr(self, 'id', None)
        return self

    async def fetch(self) -> "Document":
        """Return a fresh instance of the current document from the database.
        """
        qs = self.objects.copy()
        qs._query = self.get_query()
        return await qs.get()


class Document(DocumentBase, BaseModel):
    id: Optional[PydanticObjectId] = Field(alias='_id')

    def __init__(self, *args, **kwargs) -> None:
        BaseModel.__init__(self, *args, **self._transform(**kwargs))
        DocumentBase.__init__(self)

    class Config:
        json_encoders = {ObjectId: str}

    def _transform(self, **kwargs) -> Dict:
        """Override this method to change the input database before having it
        being validated/parsed by BaseModel (pydantic)
        """
        return kwargs
