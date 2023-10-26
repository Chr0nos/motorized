from typing import Dict, List, Literal, Optional

import pytest
from bson import ObjectId
from pymongo.results import InsertOneResult, UpdateResult

from motorized import Document, EmbeddedDocument, mark_parents
from motorized.exceptions import DocumentNotSavedError
from tests.models import Named
from tests.utils import require_db


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
    await Named.objects.filter(_id=bob.id).update(name="Louis")
    louis = await bob.fetch()

    assert louis.id == bob.id
    assert louis.name == "Louis"
    assert bob.name == "Bob"


@pytest.mark.asyncio
@require_db
async def test_save_with_custom_id():
    custom_id = ObjectId()
    bob = Named(name="bob", _id=custom_id)
    result = await bob.save(force_insert=True)
    assert isinstance(result, InsertOneResult)
    assert bob.id == custom_id

    assert isinstance(await bob.save(), UpdateResult)


def test_document_update_with_nested():
    class Chapter(EmbeddedDocument):
        name: str
        pages_count: int

    class Book(Document):
        name: str
        chapters: List[Chapter] = []

    x = Book(name="test")
    assert isinstance(x.chapters, list)
    x.chapters.append(Chapter(name="first", pages_count=0))

    x.update({"chapters": [{"name": "again", "pages_count": 42}]})
    assert x.chapters[0].pages_count == 42

    x.chapters[0].update({"name": "yay"})
    assert x.chapters[0].name == "yay"
    assert x.chapters[0].pages_count == 42
    assert callable(x.chapters[0].update)
    assert callable(x.chapters[0].deep_update)

    x.chapters[0].update({"name": "changed"})
    assert x.chapters[0].name == "changed"


@pytest.mark.asyncio
@require_db
async def test_embedded_document_privates_attributes():
    class Chapter(EmbeddedDocument):
        name: str
        _parent: Optional["Book"] = None  # noqa: F821

    class Book(Document):
        title: str
        chapters: List[Chapter]

    Chapter.model_rebuild()

    x = Book(title="irrelevant", chapters=[Chapter(name="test")])
    x.chapters[0]._parent = x
    assert x.chapters[0]._parent is x

    chapter_dict = x.chapters[0].model_dump()
    assert isinstance(chapter_dict, dict)
    assert "_parent" not in chapter_dict
    assert "name" in chapter_dict

    assert x.model_dump()["chapters"][0] == chapter_dict

    c = Chapter(name="test", _parent=40)
    assert c._parent is None
    c._parent = 42
    assert c._parent == 42


@pytest.mark.asyncio
@require_db
async def test_mark_parents():
    class Person(Document):
        name: str
        friends: list["Person"] | None = None

    Person.model_rebuild()

    tree = Person(
        name="Bob",
        friends=[
            Person(name="A"),
            Person(name="B"),
        ],
    )
    mark_parents(tree)

    assert tree._parent is None
    assert tree.friends[0]._parent is tree
    assert tree.friends[1]._parent is tree


@pytest.mark.asyncio
async def test_mark_parent_bis():
    class Item(EmbeddedDocument):
        name: str

    class Player(Document):
        inventory: Dict[str, Item] = {}
        friends: List["Player"] = []
        temper: Literal["calm", "nervous"] | None = None

    Player.model_rebuild()
    toto = Player(inventory={"gun": Item(name="gun")}, friends=[Player()], temper="calm")
    mark_parents(toto)
    assert toto._parent is None
    assert toto.inventory["gun"]._parent is toto
    assert toto.friends[0]._parent is toto
    assert isinstance(toto.model_dump(), dict)


def test_document_partial_models():
    from motorized.document import create_partial_model
    from tests.models import Player

    sub_model = create_partial_model("PlayerReader", Player, ["name", "hp"], optional=True)
    assert len(sub_model.model_fields.keys()) == 2
    for field in ("name", "hp"):
        assert field in sub_model.model_fields, field
