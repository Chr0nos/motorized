import pytest
from bson import ObjectId
from pymongo.results import InsertOneResult, UpdateResult
from pydantic import BaseModel

from tests.models import Named
from tests.utils import require_db
from typing import List, Optional

from motorized.exceptions import DocumentNotSavedError
from motorized import Document, Field, EmbeddedDocument


@pytest.mark.asyncio
@require_db
async def test_fetch_when_not_saved():
    bob = Named(name="bob")
    with pytest.raises(DocumentNotSavedError):
        await bob.fetch()


@pytest.mark.asyncio
@require_db
async def test_fetch_saved():
    bob = Named(name="Bob")
    await bob.save()
    await Named.objects.filter(_id=bob.id).update(name='Louis')
    louis = await bob.fetch()

    assert louis.id == bob.id
    assert louis.name == 'Louis'
    assert bob.name == 'Bob'


@pytest.mark.asyncio
@require_db
async def test_save_with_custom_id():
    custom_id = ObjectId()
    bob = Named(name="bob", _id=custom_id)
    result = await bob.save(force_insert=True)
    assert isinstance(result, InsertOneResult)
    assert bob.id == custom_id

    assert isinstance(await bob.save(), UpdateResult)


@pytest.mark.asyncio
@require_db
async def test_document_reader_model():
    bob = Named(name="bob")
    await bob.save()
    reader_model = bob.get_reader_model()
    reader = reader_model(**bob.dict(by_alias=True))
    assert isinstance(reader, BaseModel)
    output = reader.dict()
    assert output['id'] == bob.id

    print(bob.__fields__)
    print(reader.__fields__)

    assert reader_model.__fields__['id'].alias == '_id'


def test_document_reader_aliasing():

    class Test(Document):
        x: int = Field(alias='y')

    assert Test.__fields__['x'].alias == 'y'


def test_document_reader_with_contraints():
    class Animal(Document):
        legs: int = Field(ge=0, lt=5)

    # print(Animal.__fields__)
    # print(dir(Animal))
    reader = Animal.get_reader_model()


def test_document_update_with_nested():
    class Chapter(EmbeddedDocument):
        name: str
        pages_count: int

    class Book(Document):
        name: str
        chapters: List[Chapter] = []

    x = Book(name='test')
    assert isinstance(x.chapters, list)
    x.chapters.append(Chapter(name='first', pages_count=0))

    x.update({'chapters': [{'name': 'again', 'pages_count': 42}]})
    assert x.chapters[0].pages_count == 42

    x.chapters[0].update({'name': 'yay'})
    assert x.chapters[0].name == 'yay'
    assert x.chapters[0].pages_count == 42
    assert callable(x.chapters[0].update)
    assert callable(x.chapters[0].deep_update)

    x.chapters[0].update({'name': 'changed'})
    assert x.chapters[0].name == 'changed'


def test_document_private_override():
    class Test(Document):
        name: str
        _something: int

    x = Test(name='test')
    x._something = 42
    assert x._something == 42
    assert '_something' not in Test.get_reader_model().__fields__
    assert 'name' in Test.get_reader_model().__fields__


@pytest.mark.asyncio
@require_db
async def test_embedded_document_privates_attributes():
    from motorized.document import NoPrivateAttributes

    class Chapter(NoPrivateAttributes, EmbeddedDocument):
        name: str
        _parent: Optional["Book"] = None

    class Book(Document):
        title: str
        chapters: List[Chapter]

    Chapter.update_forward_refs()

    x = Book(title='irrelevant', chapters=[Chapter(name='test')])
    x.chapters[0]._parent = x
    assert x.chapters[0]._parent is x

    chapter_dict = x.chapters[0].dict()
    assert isinstance(chapter_dict, dict)
    assert '_parent' not in chapter_dict
    assert 'name' in chapter_dict

    assert x.dict()['chapters'][0] == chapter_dict

    c = Chapter(name='test', _parent=40)
    assert c._parent is None
    c._parent = 42
    assert c._parent == 42


@pytest.mark.asyncio
@require_db
async def test_mark_parents():
    from motorized.document import mark_parents

    class Person(Document):
        name: str
        friends: Optional[List["Person"]]

    Person.update_forward_refs()

    tree = Person(
        name='Bob',
        friends=[
            Person(name='A'),
            Person(name='B')
        ]
    )
    mark_parents(tree)

    assert tree._parent is None
    assert tree.friends[0]._parent is tree
    assert tree.friends[1]._parent is tree
