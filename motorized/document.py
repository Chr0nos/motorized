from inspect import isclass
from typing import Optional, Union, Any, Dict, Type, List, Generator
from pydantic import BaseModel, Field, validate_model
from pydantic.fields import ModelField
from pydantic.main import ModelMetaclass
from pymongo.results import InsertOneResult, UpdateResult

from motorized.queryset import QuerySet
from motorized.query import Q
from motorized.types import PydanticObjectId, ObjectId
from motorized.exceptions import DocumentNotSavedError, MotorizedError
from motorized.utils import deep_update_model


class DocumentMeta(ModelMetaclass):
    def __new__(cls, name, bases, optdict: Dict) -> Type['Document']:
        # remove any reference to `objects` in the class
        # we only declare it to be readable and conveniant with the IDE
        # the filtering of objects is only effective if you declare a class
        # to allow to give values or a real field using this name.
        try:
            objects = optdict['__annotations__']['objects']
            if isclass(objects):
                optdict['__annotations__'].pop('objects')
                optdict.pop('objects', None)
        except KeyError:
            pass

        # we allocate the BaseModel with pydantic metaclass
        instance: Type[Document] = super().__new__(cls, name, bases, optdict)
        if name not in ('Document',):
            cls._populate_default_mongo_options(
                cls, name, instance, optdict.get('Mongo'))

        class DocumentError(MotorizedError):
            pass

        class TooManyMatchException(DocumentError):
            pass

        class DocumentNotFound(DocumentError):
            pass

        instance.DocumentError = DocumentError
        instance.TooManyMatchException = TooManyMatchException
        instance.DocumentNotFound = DocumentNotFound
        instance.objects = instance.Mongo.manager_class(
            instance, getattr(instance.Mongo, 'filters', None))
        return instance

    def _populate_default_mongo_options(cls, name: str, instance: "Document",
                                        custom_mongo_settings_class) -> None:
        class Mongo:
            pass

        # forbid re-utilisation of the Mongo class between
        # inheritance of the class
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
            'local_fields': [],
            'class_name': name,
            'filters': None,
        }

        for attribute_name, default_value in default_settings.items():
            if not hasattr(instance.Mongo, attribute_name):
                setattr(instance.Mongo, attribute_name, default_value)


class Document(BaseModel, metaclass=DocumentMeta):
    objects: QuerySet
    id: Optional[PydanticObjectId] = Field(alias='_id', read_only=True)

    class Config:
        json_encoders = {ObjectId: str}
        validate_assignment = True

    class Mongo:
        manager_class = QuerySet

    def __init__(self, *args, **kwargs) -> None:
        BaseModel.__init__(self, *args, **self._transform(**kwargs))

    def get_query(self) -> Q:
        document_id = getattr(self, 'id', None)
        if not document_id:
            raise DocumentNotSavedError('document has no id.')
        return Q(_id=document_id)

    async def _create_in_db(self, creation_dict: Dict) -> InsertOneResult:
        response = await self.objects.insert_one(creation_dict)
        self.id = response.inserted_id
        return response

    async def _update_in_db(self, update_dict: Dict) -> UpdateResult:
        return await self.objects.collection.update_one(
            filter={'_id': self.id},
            update={'$set': update_dict}
        )

    @classmethod
    def _is_field_to_save(cls, field_name: str) -> bool:
        return (
            not field_name.startswith('_') and
            field_name not in cls.Mongo.local_fields and
            field_name in cls.__fields__
        )

    async def to_mongo(self) -> Dict:
        """Convert the current model dictionary to database output dict,
        this also mean the aliased fields will be stored in the alias name
        instead of their name in the document declaration.
        """
        saving_data = self.dict()

        # remove any field that is not to save, this has to be done
        # before the aliasing resolving to allow to save/load fields
        # that starts with _
        saving_data = dict(
            {
                k: v for k, v in saving_data.items()
                if self._is_field_to_save(k)
            }
        )

        # resolve all alised fields to be saved in their alias name
        for field in self._aliased_fields():
            saving_data[field.alias] = saving_data.pop(field.name, None)

        return saving_data

    async def save(self, force_insert: bool = False
    ) -> Union[InsertOneResult, UpdateResult]:
        data = await self.to_mongo()
        document_id = data.pop('_id', None)
        if document_id is None or force_insert:
            if force_insert:
                data['_id'] = document_id
            return await self._create_in_db(data)
        return await self._update_in_db(data)

    async def commit(self) -> "Document":
        """Same as `.save` but return the current instance.
        """
        await self.save()
        return self

    async def delete(self) -> "Document":
        """Delete the current instance from the database,
        to the deleted the instance need to have a .id set, in any case the
        function will return the instance itself
        """
        try:
            await self.objects.filter(self.get_query()).delete_one()
        except DocumentNotSavedError:
            pass
        setattr(self, 'id', None)
        return self

    async def fetch(self) -> "Document":
        """Return a fresh instance of the current document from the database.
        """
        return await self.objects.filter(self.get_query()).get()

    @classmethod
    def _aliased_fields(cls) -> Generator[List[ModelField], None, None]:
        """Return the list of fields with aliases
        """
        return [
            field for field in cls.__fields__.values()
            if field.name != field.alias
        ]

    def _transform(self, **kwargs) -> Dict:
        """Override this method to change the input database before having it
        being validated/parsed by BaseModel (pydantic)
        """
        return kwargs

    async def reload(self) -> "Document":
        # fetch an validate input data from database
        model_data = await self.objects.filter(self.get_query()).find_one()
        model_data.pop('_id')
        return self.update(model_data)

    def update(self, input_data: Dict) -> "Document":
        """Update the current instance with the given `input_data` after
        validation return the object itself (without saving it in the database)
        """
        validate_model(self, input_data)
        allow_extra: bool = getattr(self.Config, 'extra', 'ignore') == 'allow'

        # load the fields into the current instance
        for field, value in input_data.items():
            if allow_extra or hasattr(self, field):
                setattr(self, field, value)
        return self

    def deep_update(self, input_data: Dict, **kwargs) -> "Document":
        return deep_update_model(self, input_data, **kwargs)

    def __repr__(self):
        def get_field_entry(field: Field) -> str:
            return f"{field.name}={getattr(self, field.name)}"

        fields = ", ".join([
            get_field_entry(field)
            for field in self.__fields__.values()
            if field.name not in self.Mongo.local_fields
        ])
        return f'{self.__class__.__name__}({fields})'

    def __setattr__(self, name: str, value: Any) -> None:
        # allow any private attribute to be passed
        if name.startswith('_') or name in self.Mongo.local_fields:
            return object.__setattr__(self, name, value)

        # otherwise we let pydantic decide
        return super().__setattr__(name, value)

    @classmethod
    def get_readonly_fields(cls):
        return list([
            field_name
            for field_name, field in cls.__fields__.items()
            if field.field_info.extra.get('read_only', False)
        ])

    @classmethod
    def get_updater_model(cls) -> Type[BaseModel]:
        """This class factory function create a new BaseModel from this model
        with all the fields that are not marked as `read_only`, all the fields
        are optional in the generated model
        """
        ignore = cls.get_readonly_fields() + list(cls.Mongo.local_fields)
        fields = dict({
            field_name: field for field_name, field in cls.__fields__.items()
            if field_name not in ignore
        })

        optdict = {
            '__annotations__': {
                field_name: Optional[field.type_]
                for field_name, field in fields.items()
            },
            **{
                field_name: field.field_info
                for field_name, field in fields.items()
            }
        }
        updater = type('ModelUpdater', (BaseModel,), optdict)
        return updater
