from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from typing import Optional, Union, Any, Optional, Dict, Type, List, Generator
from pydantic import BaseModel, Field
from pydantic.fields import ModelField
from pydantic.main import ModelMetaclass
from pymongo.results import InsertOneResult, UpdateResult

from motorized.queryset import QuerySet
from motorized.query import Q
from motorized.types import PydanticObjectId, ObjectId
from motorized.exceptions import DocumentNotSavedError, MotorizedError


def show_class_constructor(cls, name, bases, optdict: Dict):
    print(' --- ')
    print('cls', cls)
    print('name', name)
    print('bases:', *bases)
    print('opts', optdict)


class DocumentMeta(ModelMetaclass):
    def __new__(cls, name, bases, optdict: Dict) -> Type['Document']:
        # optdict.pop('objects', None)
        # optdict.pop('__annotations__', {}).pop('objects', None)
        # show_class_constructor(cls, name, bases, optdict)
        instance: Type[Document] = super().__new__(cls, name, bases, optdict)
        if name not in ('Document',):
            cls._populate_default_mongo_options(cls, name, instance, optdict.get('Mongo'))

        class DocumentError(MotorizedError):
            pass

        class TooManyMatchException(DocumentError):
            pass

        class DocumentNotFound(DocumentError):
            pass

        instance.DocumentError = DocumentError
        instance.TooManyMatchException = TooManyMatchException
        instance.DocumentNotFound = DocumentNotFound
        instance.objects = instance.Mongo.manager_class(instance)
        return instance

    def _populate_default_mongo_options(cls, name: str, instance: "Document",
                                        custom_mongo_settings_class) -> None:
        class Mongo:
            pass

        # forbid re-utilisation of the Mongo class between inheritance of the class
        try:
            if instance.Mongo.class_name != name:
                instance.Mongo = Mongo()
        except AttributeError:
            pass

        if custom_mongo_settings_class:
            instance.Mongo = custom_mongo_settings_class

        default_settings = {
            'collection': name.lower() + 's',
            'manager_class': QuerySet,
            'class_name': name
        }

        for attribute_name, default_value in default_settings.items():
            if not hasattr(instance.Mongo, attribute_name):
                setattr(instance.Mongo, attribute_name, default_value)


class Document(BaseModel, metaclass=DocumentMeta):
    # objects: QuerySet
    id: Optional[PydanticObjectId] = Field(alias='_id')

    class Config:
        json_encoders = {ObjectId: str}

    class Mongo:
        manager_class = QuerySet

    def __init__(self, *args, **kwargs) -> None:
        BaseModel.__init__(self, *args, **self._transform(**kwargs))

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
        """Return the list of fields with aliases
        """
        return [field for field in cls.__fields__.values() if field.name != field.alias]

    def _transform(self, **kwargs) -> Dict:
        """Override this method to change the input database before having it
        being validated/parsed by BaseModel (pydantic)
        """
        return kwargs
