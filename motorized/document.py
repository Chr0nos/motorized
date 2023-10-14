from inspect import isclass
from typing import Any, Dict, Generator, Self, Type, get_origin

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.fields import FieldInfo
from pydantic_partial import PartialModelMixin
from pymongo.results import InsertOneResult, UpdateResult

from motorized.exceptions import DocumentNotSavedError, MotorizedError
from motorized.query import Q
from motorized.queryset import QuerySet
from motorized.utils import deep_update_model


class DocumentMeta(ModelMetaclass):
    def __new__(cls, name, bases, optdict: Dict, **kwargs) -> Type["Document"]:
        # remove any reference to `objects` in the class
        # we only declare it to be readable and conveniant with the IDE
        # the filtering of objects is only effective if you declare a class
        # to allow to give values or a real field using this name.
        try:
            objects = optdict["__annotations__"]["objects"]
            if isclass(objects):
                optdict["__annotations__"].pop("objects")
                optdict.pop("objects", None)
        except KeyError:
            pass

        # we allocate the BaseModel with pydantic metaclass
        instance: Type[Document] = super().__new__(cls, name, bases, optdict, **kwargs)
        if name not in ("Document",):
            cls._populate_default_mongo_options(cls, name, instance, optdict.get("Mongo"))

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
            instance, getattr(instance.Mongo, "filters", None)
        )
        return instance

    def _populate_default_mongo_options(
        cls, name: str, instance: "Document", custom_mongo_settings_class
    ) -> None:
        class Mongo:
            pass

        # forbid re-utilisation of the Mongo class between
        # inheritance of the class except for the `manager_class` parameter
        previous_manager_class = None
        try:
            if instance.Mongo.class_name != name:
                instance.Mongo = Mongo()
                previous_manager_class = instance.Mongo.manager_class
        except AttributeError:
            pass

        if custom_mongo_settings_class:
            instance.Mongo = custom_mongo_settings_class

        default_settings = {
            "collection": name.lower() + "s",
            "manager_class": previous_manager_class or QuerySet,
            "local_fields": [],
            "class_name": name,
            "filters": None,
        }

        for attribute_name, default_value in default_settings.items():
            if not hasattr(instance.Mongo, attribute_name):
                setattr(instance.Mongo, attribute_name, default_value)


class DocumentBasis(PartialModelMixin):
    """Represent the very bassis of Document and EmbeddedDocument"""

    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    def update(self, input_data: dict) -> Self:
        """Update the current instance with the given `input_data` after
        validation return the object itself (without saving it in the database)
        """
        self.model_validate(self.model_dump() | input_data)
        allow_extra: bool = getattr(self.model_config, "extra", "ignore") == "allow"

        # load the fields into the current instance
        for field, value in input_data.items():
            if allow_extra or hasattr(self, field):
                setattr(self, field, value)
        return self

    def deep_update(self, input_data: dict, **kwargs) -> Self:
        return deep_update_model(self, input_data, **kwargs)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            return object.__setattr__(self, name, value)

        return super().__setattr__(name, value)


class EmbeddedDocument(DocumentBasis):
    pass


class Document(DocumentBasis, metaclass=DocumentMeta):
    objects: QuerySet
    id: ObjectId | None = Field(alias="_id", default=None)

    # @classmethod
    # def objects(cls) -> QuerySet[Self]:
    #     return cls.Mongo.manager_class(cls)

    class Mongo:
        manager_class = QuerySet

    def __init__(self, *args, **kwargs) -> None:
        BaseModel.__init__(self, *args, **self._transform(**kwargs))

    @field_serializer("id")
    def serialize_id(self, value: ObjectId, _info) -> str:
        return str(value)

    def get_query(self) -> Q:
        document_id = getattr(self, "id", None)
        if not document_id:
            raise DocumentNotSavedError("document has no id.")
        return Q(_id=document_id)

    async def _create_in_db(self, creation_dict: Dict) -> InsertOneResult:
        response = await self.objects.insert_one(creation_dict)
        self.id = response.inserted_id
        return response

    async def _update_in_db(self, update_dict: Dict) -> UpdateResult:
        return await self.objects.collection.update_one(
            filter={"_id": self.id}, update={"$set": update_dict}
        )

    @classmethod
    def _is_field_to_save(cls, field_name: str) -> bool:
        return (
            not field_name.startswith("_")
            and field_name not in cls.Mongo.local_fields
            and field_name in cls.model_fields
        )

    async def to_mongo(self) -> Dict:
        """Convert the current model dictionary to database output dict,
        this also mean the aliased fields will be stored in the alias name
        instead of their name in the document declaration.
        """
        saving_data = self.model_dump()

        # remove any field that is not to save, this has to be done
        # before the aliasing resolving to allow to save/load fields
        # that starts with _
        saving_data = dict({k: v for k, v in saving_data.items() if self._is_field_to_save(k)})

        # resolve all alised fields to be saved in their alias name
        for field_name, field in self._aliased_fields():
            saving_data[field.alias] = saving_data.pop(field_name, None)

        return saving_data

    async def save(self, force_insert: bool = False) -> InsertOneResult | UpdateResult:
        data = await self.to_mongo()
        data.pop("_id", None)
        if self.id is None or force_insert:
            if force_insert:
                data["_id"] = self.id
            return await self._create_in_db(data)
        return await self._update_in_db(data)

    async def commit(self) -> Self:
        """Same as `.save` but return the current instance."""
        await self.save()
        return self

    async def delete(self) -> Self:
        """Delete the current instance from the database,
        to the deleted the instance need to have a .id set, in any case the
        function will return the instance itself
        """
        try:
            await self.objects.filter(self.get_query()).delete_one()
        except DocumentNotSavedError:
            pass
        setattr(self, "id", None)
        return self

    async def fetch(self) -> Self:
        """Return a fresh instance of the current document from the database."""
        return await self.objects.filter(self.get_query()).get()

    @classmethod
    def _aliased_fields(cls) -> Generator[tuple[str, FieldInfo], None, None]:
        """Return the list of fields with aliases"""
        return [
            (name, field)
            for name, field in cls.model_fields.items()
            if name != field.alias and field.alias
        ]

    def _transform(self, **kwargs) -> dict:
        """Override this method to change the input database before having it
        being validated/parsed by BaseModel (pydantic)
        """
        return kwargs

    async def reload(self) -> Self:
        # fetch an validate input data from database
        model_data = await self.objects.filter(self.get_query()).find_one()
        model_data.pop("_id")
        return self.update(model_data)

    def __repr__(self):
        def get_field_entry(field_name: str) -> str:
            return f'{field_name}="{getattr(self, field_name)}"'

        fields = ", ".join(
            [
                get_field_entry(field_name)
                for field_name in self.model_fields.keys()
                if field_name not in self.Mongo.local_fields
            ]
        )
        return f"{self.__class__.__name__}({fields})"


def mark_parents(model: DocumentBasis, parent: DocumentBasis | None = None) -> None:
    """Mark all nested items with a `_parent` attribute pointing to their
    parent instance (for trees of DocumentBasis)

    it is strongly recomemded to use this on classes with the
    `PrivatesAttrsMixin` mixin to avoid ciruclar loop when calling the
    .dict method.
    """
    model._parent = parent
    for field_name, field in model.model_fields.items():
        item = getattr(model, field_name)

        if isinstance(item, BaseModel):
            mark_parents(item, model)

        elif type(item) in (list, tuple):
            for submodel in item:
                mark_parents(submodel, model)

        elif isinstance(item, dict):
            for submodel in item.values():
                mark_parents(submodel, model)
