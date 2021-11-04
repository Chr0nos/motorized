import pytest

from tests.models import Player, Named

from pydantic import BaseModel
from typing import Optional, Any
from bson.objectid import ObjectId

from motorized import connection, Document, QuerySet
from motorized.exceptions import DocumentNotSavedError, NotConnectedException


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


@pytest.mark.asyncio
async def test_local_fields():
    class Book(Document):
        name: str
        extra: int

        class Mongo:
            local_fields = ('extra',)

    book = Book(name='lotr', extra=2)
    book_data = await book.to_mongo()
    assert book_data['name'] == book.name
    assert 'extra' not in book_data


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

    assert 'name' in Alumni.__fields__
    assert 'age' in Alumni.__fields__
    assert 'finished_year' in Alumni.__fields__


def test_inheritance_stacking():
    class Alpha(Document):
        alpha: bool = True

    class Bravo(Alpha):
        bravo: bool = True

    class Charlie(Document):
        charlie: bool = True

    class Delta(Charlie, Bravo):
        delta: bool = True

    for field in ('alpha', 'bravo', 'charlie', 'delta'):
        assert field in Delta.__fields__, field


@pytest.mark.asyncio
async def test_private_attributes():
    class Scrapper(Document):
        url: str
        _page_content: Optional[Any] = None

    x = Scrapper(url='google.com')
    saving_data = await x.to_mongo()
    assert '_page_content' not in saving_data
    assert 'url' in saving_data
    assert not Scrapper._is_field_to_save('_page_content')

    x._other = True

    # we don't want to allow inserting private values from the constructor
    # to avoid malicious code to come from the database into the python object.
    y = Scrapper(url='test', _page_content='test')
    assert y._page_content is None


def test_queryset_inheritance():
    class UserManager(QuerySet):
        pass

    class User(Document):
        class Mongo:
            manager_class = UserManager

    assert isinstance(User.objects, UserManager)
    assert isinstance(User.objects.copy(), UserManager), \
        type(User.objects.copy())


def test_get_query():
    class Book(Document):
        pass

    book = Book()
    book.id = ObjectId()

    assert book.get_query().query == {'_id': book.id}


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
async def test_document_updater():
    billy = Player(
        name='Billy',
        position={"x": 0.0, "y": 1.0, "z": 1.0}
    )
    assert Player.get_readonly_fields() == ['id', 'name', 'golds', 'hp']
    model = Player.get_updater_model()
    payload = {
        "id": "ignore me",
        "name": "Simon",
        "position": {"x": 2.0, "w": 4.0},
        "ignore_me": True,
        "hp": {"left": 42}
    }
    data = model(**payload).dict(exclude_unset=True)
    billy.deep_update(data)
    assert billy.position == {"x": 2.0, "y": 1.0, "z": 1.0}
    assert billy.name == 'Billy'
    assert billy.id is None
    assert not hasattr(billy, "ignore_me")
    assert billy.hp.left == 10, "this field is read only"

    # this update should reset the positions since a None has been
    # passed as position.
    billy.deep_update({'position': None})
    assert billy.position == {'x': 0.0, 'y': 0.0, 'z': 0.0}

    billy.position = {'x': 10.0, 'y': 10.0, 'z': 10.0}
    # this update should leave the actual positions as they are since no values
    # were changed
    billy.deep_update({'position': {}})
    assert billy.position == {'x': 10.0, 'y': 10.0, 'z': 10.0}

    # this update should reset the positions
    billy.update({'position': {}})
    assert billy.position == {"x": 0.0, "y": 0.0, "z": 0.0}

    assert isinstance(billy.__repr__(), str)


@pytest.mark.asyncio
async def test_document_delete_without_id():
    bob = Named(name="bob")
    await bob.delete()
    assert bob.name == "bob"
    assert bob.id is None
