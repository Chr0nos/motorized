from typing import Any, Optional, get_args

import pytest
from bson.objectid import ObjectId
from pydantic import BaseModel

from motorized import Document, QuerySet, connection
from motorized.exceptions import DocumentNotSavedError, NotConnectedException
from tests.models import Named, Player


def test_document_type():
    class User(Document):
        pass

    x = User()
    assert isinstance(x, BaseModel)


def test_collection_resolver_basic():
    class User(Document):
        pass

    assert User.Mongo.collection == "users"


def test_collection_resolver_nested():
    class User(Document):
        pass

    class Student(User):
        pass

    assert Student.Mongo.collection == "students"


def test_collection_forcing():
    class User(Document):
        class Mongo:
            collection = "forced"

    class Student(User):
        pass

    class Alumni(Student):
        class Mongo:
            collection = "ancients"

    assert User.Mongo.collection == "forced"
    assert Student.Mongo.collection == "students"
    assert Alumni.Mongo.collection == "ancients"


def test_document_has_objects():
    assert isinstance(Document.objects, QuerySet)


def test_document_custom_manager_class():
    class BookManager(QuerySet):
        pass

    class Book(Document):
        class Mongo:
            manager_class = BookManager

    class Encyclopedia(Book):
        pass

    assert isinstance(Book.objects, BookManager)
    assert isinstance(Encyclopedia.objects, QuerySet) and not isinstance(
        Encyclopedia.objects, BookManager
    )


@pytest.mark.asyncio
async def test_local_fields():
    class Book(Document):
        name: str
        extra: int

        class Mongo:
            local_fields = ("extra",)

    book = Book(name="lotr", extra=2)
    book_data = await book.to_mongo()
    assert book_data["name"] == book.name
    assert "extra" not in book_data


def test_attributes_inheritance():
    class Personn(Document):
        name: str
        age: int

    class Student(Personn):
        degree: str
        year: int

    class Foo:
        @property
        def bar() -> bool:
            return True

    class Alumni(Foo, Student):
        finished_year: int

    assert "name" in Alumni.model_fields
    assert "age" in Alumni.model_fields
    assert "finished_year" in Alumni.model_fields


def test_inheritance_stacking():
    class Alpha(Document):
        alpha: bool = True

    class Bravo(Alpha):
        bravo: bool = True

    class Charlie(Document):
        charlie: bool = True

    class Delta(Charlie, Bravo):
        delta: bool = True

    for field in ("alpha", "bravo", "charlie", "delta"):
        assert field in Delta.model_fields, field


@pytest.mark.asyncio
async def test_private_attributes():
    class Scrapper(Document):
        url: str
        _page_content: Optional[Any] = None

    x = Scrapper(url="google.com")
    saving_data = await x.to_mongo()
    assert "_page_content" not in saving_data
    assert "url" in saving_data
    assert not Scrapper._is_field_to_save("_page_content")

    x._other = True

    # we don't want to allow inserting private values from the constructor
    # to avoid malicious code to come from the database into the python object.
    y = Scrapper(url="test", _page_content="test")
    assert y._page_content is None


def test_queryset_inheritance():
    class UserManager(QuerySet):
        pass

    class User(Document):
        class Mongo:
            manager_class = UserManager

    assert isinstance(User.objects, UserManager)
    assert isinstance(User.objects.copy(), UserManager), type(User.objects.copy())


def test_get_query():
    class Book(Document):
        pass

    book = Book()
    book.id = ObjectId()

    assert book.get_query().query == {"_id": book.id}


def test_get_query_not_saved():
    class Book(Document):
        pass

    book = Book()
    with pytest.raises(DocumentNotSavedError):
        book.get_query()


@pytest.mark.asyncio
async def test_not_connected():
    connection.client = True
    connection.database = True
    await connection.disconnect()
    assert not connection.client
    assert not connection.database
    with pytest.raises(NotConnectedException):
        Document.objects.collection


@pytest.mark.asyncio
async def test_document_delete_without_id():
    bob = Named(name="bob")
    await bob.delete()
    assert bob.name == "bob"
    assert bob.id is None
