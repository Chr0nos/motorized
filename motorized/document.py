from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from typing import Optional, Tuple, Union, Any, Optional, Dict, Type, List, Generator
from pydantic import BaseModel, Field
from pydantic.fields import ModelField
from pydantic.main import ModelMetaclass
from pymongo.results import InsertOneResult, UpdateResult

from motorized.queryset import QuerySet
from motorized.query import Q
from motorized.types import PydanticObjectId, ObjectId
from motorized.exceptions import DocumentNotSavedError, MotorizedError


class DocumentMeta(ModelMetaclass):
    def __new__(cls, name, bases, optdict: Dict) -> Type['DocumentBase']:
        instance: Type[DocumentBase] = super().__new__(cls, name, bases, optdict)
        manager_class = getattr(instance.Mongo, 'manager_class', QuerySet)
        instance.objects = manager_class(instance)
        # print(name, instance.Mongo.collection)
        if instance.Mongo.collection is None and name not in ('Document', 'DocumentBase'):
            instance.Mongo.collection = name.lower() + 's'

        class DocumentError(MotorizedError):
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

    async def _update(self, update_dict: Dict) -> UpdateResult:
        return await self.objects.collection.update_one(
            filter={'_id': self.id},
            update={'$set': update_dict}
        )

    async def to_mongo(self) -> Dict:
        """Convert the current model dictionary to database output dict,
        this also mean the aliased fields will be stored in the alias name instead of their
        name in the document declaration.
        """
        saving_data = self.dict()
        for field in self._aliased_fields():
            saving_data[field.alias] = saving_data.pop(field.name, None)
        return saving_data

    async def save(self) -> Union[InsertOneResult, UpdateResult]:
        data = await self.to_mongo()
        document_id = data.pop('_id', None)
        if document_id is None:
            return await self._create(data)
        return await self._update(data)

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

    @classmethod
    def _aliased_fields(cls) -> Generator[List[ModelField], None, None]:
        return [field for field in cls.__fields__.values() if field.name != field.alias]


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
