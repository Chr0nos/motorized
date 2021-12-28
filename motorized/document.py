from inspect import isclass
from typing import Optional, Union, Any, Dict, Type, List, Generator, Literal, Tuple
from pydantic import BaseModel, Field, validate_model
from pydantic.fields import ModelField
from pydantic.main import ModelMetaclass
from pymongo.results import InsertOneResult, UpdateResult

from motorized.queryset import QuerySet
from motorized.query import Q
from motorized.types import PydanticObjectId, ObjectId
from motorized.exceptions import DocumentNotSavedError, MotorizedError
from motorized.utils import (
    deep_update_model, get_all_fields_names,
    model_map, dynamic_model_node_factory
)


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


class DocumentBasis(BaseModel):
    """Represent the very bassis of Document and EmbeddedDocument
    """
    class Config:
        json_encoders = {ObjectId: str}
        validate_assignment = True

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

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith('_'):
            return object.__setattr__(self, name, value)

        return super().__setattr__(name, value)


class PrivatesAttrsMixin:
    """Ommit any private arributes from iterators and .dict method on this
    document.
    """
    class Config:
        json_encoders = {ObjectId: str}
        validate_assignment = True
        underscore_attrs_are_private = True

    def __iter__(self) -> Generator[str, Any, None]:
        for field_name, field_value in super().__iter__():
            if field_name not in self.__fields__:
                continue
            yield field_name, field_value

    def dict(self, **kwargs) -> Dict[str, Any]:
        return dict({
            field_name: field_value
            if not isinstance(field_value, BaseModel)
            else field_value.dict(**kwargs)
            for field_name, field_value in self
        })


class EmbeddedDocument(DocumentBasis):
    pass


class Document(DocumentBasis, metaclass=DocumentMeta):
    objects: QuerySet
    id: Optional[PydanticObjectId] = Field(alias='_id', read_only=True)

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

    async def save(
        self,
        force_insert: bool = False
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

    def __repr__(self):
        def get_field_entry(field: Field) -> str:
            return f"{field.name}={getattr(self, field.name)}"

        fields = ", ".join([
            get_field_entry(field)
            for field in self.__fields__.values()
            if field.name not in self.Mongo.local_fields
        ])
        return f'{self.__class__.__name__}({fields})'

    # def __setattr__(self, name: str, value: Any) -> None:
    #     # allow any private attribute to be passed
    #     if name.startswith('_') or name in self.Mongo.local_fields:
    #         return object.__setattr__(self, name, value)

    #     # otherwise we let pydantic decide
    #     return super().__setattr__(name, value)

    @classmethod
    def get_readonly_fields(cls):
        return list(cls.get_marked_fields('read_only').keys())

    @classmethod
    def get_marked_fields(
            cls, mark: str,
            value=True,
            default=False
    ) -> Dict[str, ModelField]:
        return dict({
            field_name: field
            for field_name, field in cls.__fields__.items()
            if field.field_info.extra.get(mark, default) == value
        })

    @classmethod
    def get_updater_model(
        cls,
        exclude: Optional[List[Tuple[BaseModel, Optional[List[str]]]]] = None
    ) -> Type[BaseModel]:
        return cls.get_filtered_model(exclude, ['read_only', 'private'])

    @classmethod
    def get_reader_model(
        cls,
        exclude: Optional[List[Tuple[BaseModel, Optional[List[str]]]]] = None,
        exclude_fields_marks: Optional[List[str]] = None
    ) -> Type[BaseModel]:
        if exclude_fields_marks is None:
            exclude_fields_marks = []
        reader = cls.get_filtered_model(exclude, ['private'] + exclude_fields_marks)
        model = type(cls.__name__ + 'Reader', (reader,), {})
        return model

    @classmethod
    def get_filtered_model(
        cls,
        exclude: Optional[List[Tuple[BaseModel, Optional[List[str]]]]] = None,
        exclude_fields_marks: Optional[List[str]] = None
    ) -> Type[BaseModel]:
        """This class factory function create a new BaseModel from this model
        with all the fields that are not marked as `read_only`, all the fields
        are optional in the generated model

        exemple:
        ```python
        updater = User.get_updater_model(exclude=[(User, ['password'])])
        ```
        """
        def is_excluded(model: BaseModel, field: ModelField) -> bool:
            if not exclude:
                return False
            for exclude_model, exclude_field_names in exclude.items():
                if model == exclude_model:
                    if exclude_field_names is None:
                        return True
                    if field.field_info.name in exclude_field_names:
                        return True
            return False

        def field_filtering(model: BaseModel,
                            field: ModelField) -> Optional[ModelField]:
            if is_excluded(model, field):
                return None
            if exclude_fields_marks:
                for mark in exclude_fields_marks:
                    if field.field_info.extra.get(mark):
                        return None
            if field.name in cls.Mongo.local_fields:
                return None
            return field

        return model_map(cls, field_filtering, dynamic_model_node_factory, True)

    @classmethod
    def get_public_ordering_fields(cls) -> Literal:
        """Return a literal with all visibles fields from an external use
        perspective (ignore all Fields(private=True))
        """
        def is_ignored(field_name: str, field: ModelField) -> bool:
            if field.field_info.extra.get('private', False):
                return True
            if field_name in cls.Mongo.local_fields:
                return True
            return False

        fields = get_all_fields_names(cls, field_skip_func=is_ignored)
        fields.extend([f'-{field_name}' for field_name in fields])
        fields.sort(key=lambda x: x if not x.startswith('-') else x[1:])
        return Literal[tuple(fields)]


def mark_parents(
    model: DocumentBasis,
    parent: Optional[DocumentBasis] = None
) -> None:
    """Mark all nested items with a `_parent` attribute pointing to their
    parent instance (for trees of DocumentBasis)

    it is strongly recomemded to use this on classes with the
    `PrivatesAttrsMixin` mixin to avoid ciruclar loop when calling the
    .dict method.
    """
    model._parent = parent
    for field in model.__fields__.values():
        field: ModelField = field
        if not issubclass(field.type_, DocumentBasis):
            continue

        item = getattr(model, field.name)
        if isinstance(item, DocumentBasis):
            mark_parents(item, model)

        elif isinstance(item, list):
            for submodel in item:
                mark_parents(submodel, model)

        elif isinstance(item, dict):
            for submodel in item.values():
                mark_parents(submodel, model)
