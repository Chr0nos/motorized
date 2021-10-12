from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from typing import Optional, Union, Any, Optional, Dict, Type
from pydantic import BaseModel, Field
from pydantic.main import ModelMetaclass
from pymongo.results import InsertOneResult

from motorized.queryset import QuerySet
from motorized.query import Q
from motorized.types import PydanticObjectId, ObjectId


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

    def get_query(self, id_field: str = 'id') -> Q:
        document_id = getattr(self, id_field)
        if not document_id:
            raise ValueError('document has no id.')
        return Q(**{id_field: document_id})

    async def save(self, id_field: str = 'id'):
        data = self.dict()
        document_id = data.get(id_field, None)
        if document_id is None:
            data.pop(id_field, None)
            response = await self.objects.collection.insert_one(data)
            if isinstance(response, InsertOneResult):
                self.id = response.inserted_id
        else:
            response = await self.objects.collection.update_one(
                filter={id_field: document_id},
                update={'$set': data}
            )
        return response

    async def delete(self, id_field: str = 'id'):
        document_id = getattr(self, id_field)
        if not document_id:
            return
        await self.objects.filter(**{id_field: document_id}).delete_one()
        setattr(self, id_field, None)
        return self

    # async def reload(self, id_field: str = 'id'):
    #     document_id = getattr(self, id_field, None)
    #     if not document_id:
    #         raise ValueError('missing document id, use .save() first')
    #     document = await self.objects.filter(**{id_field: document_id}).get()
    #     self.__dict__ = document.dict()
    #     return self


class Document(DocumentBase, BaseModel):
    id: Optional[PydanticObjectId] = Field(alias='id')

    def __init__(self, *args, **kwargs) -> None:
        document_id = kwargs.pop('_id', None)
        if document_id:
            kwargs.setdefault('id', document_id)
        BaseModel.__init__(self, *args, **kwargs)
        DocumentBase.__init__(self)

    class Config:
        json_encoders = {ObjectId: str}
