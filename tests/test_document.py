import pytest
from bson import ObjectId
from pymongo.results import InsertOneResult, UpdateResult
from pydantic import BaseModel

from tests.models import Named
from tests.utils import require_db
from typing import List

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
