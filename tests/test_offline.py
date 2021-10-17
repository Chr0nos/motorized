import asyncio
from motorized.document import Document
from motorized.queryset import QuerySet
from pydantic import BaseModel


def test_document_type():
    class User(Document):
        pass

    x = User()
    assert isinstance(x, BaseModel)


def test_collection_resolver_basic():
    class User(Document):
        pass

    assert User.Mongo.collection == 'users'


def test_collection_resolver_nested():
    class User(Document):
        pass

    class Student(User):
        pass

    assert Student.Mongo.collection == 'students'


def test_collection_forcing():
    class User(Document):
        class Mongo:
            collection = 'forced'

    class Student(User):
        pass

    class Alumni(Student):
        class Mongo:
            collection = 'ancients'

    assert User.Mongo.collection == 'forced'
    assert Student.Mongo.collection == 'students'
    assert Alumni.Mongo.collection == 'ancients'


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
    assert isinstance(Encyclopedia.objects, QuerySet) and \
        not isinstance(Encyclopedia.objects, BookManager)


def test_local_fields():
    class Book(Document):
        name: str
        extra: int

        class Mongo:
            local_fields = ('extra',)

    book = Book(name='lotr', extra=2)
    book_data = asyncio.run(book.to_mongo())
    assert book_data['name'] == book.name
    assert 'extra' not in book_data
