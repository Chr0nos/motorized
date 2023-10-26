import pytest
from pymongo.results import UpdateResult

from motorized import Document, Q
from motorized.exceptions import DocumentNotSavedError
from tests.models import Book, Named
from tests.utils import require_db


@pytest.mark.asyncio
@require_db
async def test_queryset_all():
    assert await Book.objects.all() == []

    book = await Book.objects.create(name="test", saga="test", pages=1, volume=1)
    books = await Book.objects.all()
    assert len(books) == 1
    assert isinstance(books, list)
    assert books[0] == book


@pytest.mark.asyncio
@require_db
async def test_queryset_async_iter():
    await Book.objects.create(name="test", pages=1, volume=1)
    await Book.objects.create(name="test", pages=1, volume=2)

    expected_volume = 1
    async for book in Book.objects.order_by(["volume"]):
        assert isinstance(book, Book)
        assert book.volume == expected_volume
        expected_volume += 1
    assert expected_volume == 3


@pytest.mark.asyncio
@require_db
async def test_map():
    await Book.objects.create(name="test", pages=1, volume=1)
    await Book.objects.create(name="toto", pages=40, volume=2)

    async def mapping_function(book: Book) -> int:
        return book.pages * 2

    result = await Book.objects.map(mapping_function)
    assert result == [2, 80]


@pytest.mark.asyncio
@require_db
async def test_get_simple():
    await Book.objects.create(name="entropy", pages=1, volume=2)
    await Book.objects.create(name="test", pages=1, volume=4)

    book = await Book.objects.get(name="test")
    assert book.name == "test"


@pytest.mark.asyncio
@require_db
async def test_get_too_many_results():
    await Book.objects.create(name="a", pages=1, volume=1)
    await Book.objects.create(name="a", pages=4, volume=2)
    with pytest.raises(Book.TooManyMatchException):
        await Book.objects.get(name="a")


@pytest.mark.asyncio
@require_db
async def test_get_no_result():
    await Book.objects.delete()
    with pytest.raises(Book.DocumentNotFound):
        await Book.objects.get(name="nope")


@pytest.mark.asyncio
@require_db
async def test_commit():
    book = Book(name="test", pages=42, volume=3)
    assert await book.commit() == book
    assert book.id


@pytest.mark.asyncio
@require_db
async def test_reload():
    book = await Book.objects.create(name="test", pages=42, volume=3)
    # simulate a side effect, like an other process had changed the book
    await Book.objects.collection.update_one({"_id": book.id}, {"$set": {"volume": 1}})

    await book.reload()
    assert book.volume == 1
    assert book.name == "test"
    assert book.pages == 42


@pytest.mark.asyncio
@require_db
async def test_get_first():
    await Named.objects.create(name="C3PO")

    x = await Named.objects.first()
    assert x.name == "C3PO"


@pytest.mark.asyncio
@require_db
async def test_get_first_with_no_match():
    await Named.objects.delete()
    await Named.objects.create(name="rabbit")
    x = await Named.objects.filter(name="carott").first()
    assert x is None
    assert (await Named.objects.filter(name="rabbit").first()).name == "rabbit"


@pytest.mark.asyncio
@require_db
async def test_drop_collection():
    await Named.objects.create(name="abc")
    await Named.objects.create(name="def")
    await Named.objects.drop()
    assert await Named.objects.count() == 0


@pytest.mark.asyncio
@require_db
async def test_values_list():
    names = ["zack", "alice", "bob", "brian", "hector"]
    for name in names:
        await Named.objects.create(name=name)

    values = await Named.objects.order_by(["name"]).values_list("name", flat=True)
    assert values == sorted(names)


@pytest.mark.asyncio
@require_db
async def test_or():
    class User(Document):
        first_name: str
        last_name: str

    charles = await User.objects.create(first_name="charles", last_name="dwarf")
    alice = await User.objects.create(first_name="alice", last_name="cooper")
    bob = await User.objects.create(first_name="bob", last_name="robberts")

    query = Q(first_name="charles") | Q(last_name="cooper")
    result = await User.objects.filter(query).all()
    assert charles in result
    assert alice in result
    assert bob not in result


@pytest.mark.asyncio
@require_db
async def test_delete():
    zack = await Named.objects.create(name="zack")
    alice = await Named.objects.create(name="alice")

    await zack.delete()
    with pytest.raises(DocumentNotSavedError):
        await zack.reload()
    await alice.reload()


# @pytest.mark.asyncio
# @require_db
# async def test_session():
#     await Book.objects.create(name='foo', pages=1, volume=1)

#     async with await connection.client.start_session() as session:
#         session.start_transaction()
#         queryset = Book.objects.use_session(session)
#         assert queryset._session == session
#         await queryset.delete()
#         await session.abort_transaction()

#     assert await Book.objects.count() == 1


@pytest.mark.asyncio
@require_db
async def test_queryset_override_collection_name():
    assert Book.objects.collection.name == "books"
    with Book.objects.collection_name("migrate"):
        assert Named.objects.collection.name == "nameds"
        assert Book.objects.collection.name == "migrate"
    assert Book.objects.collection.name == "books"


@pytest.mark.asyncio
@require_db
async def test_queryset_update():
    foo = await Book.objects.create(name="Foo", pages=1, volume=1)
    blah = await Book.objects.create(name="Blah", pages=42, volume=3)

    update = await Book.objects.filter(name="Foo").update(pages=100, volume=2)
    assert isinstance(update, UpdateResult)
    await foo.reload()
    assert foo.pages == 100
    assert foo.volume == 2

    await blah.reload()
    assert blah.pages == 42
    assert blah.volume == 3

    await Book.objects.update(added_field=True)
    foo_dict = await Book.objects.filter(foo.get_query()).find_one()
    assert foo_dict["added_field"] is True


@pytest.mark.asyncio
@require_db
async def test_queryset_unset():
    foo = await Book.objects.create(name="foo", pages=0, volume=0)
    await Book.objects.create(name="test", volume=1, pages=42)
    await Book.objects.filter(name="test").unset(["pages", "volume"])
    data = await Book.objects.filter(name="test").find_one()
    assert data["name"] == "test"
    assert "pages" not in data
    assert "volume" not in data
    assert "_id" in data
    await foo.reload()


@pytest.mark.asyncio
@require_db
async def test_queryset_aggregation_pagination():
    for letter in "abcdef":
        await Named.objects.create(name=letter)
    await Named.objects.update(extra=1)

    lst = await Named.objects.order_by(["name"]).limit(3).skip(3).values_list("name", flat=True)
    assert lst == ["d", "e", "f"]

    # here we are testing the QuerySet._agregate pagination
    sum_extra = Named.objects.order_by(["name"]).skip(3).limit(3).sum("extra")
    assert await sum_extra == 3

    sum_extra = Named.objects.order_by(["name"]).skip(3).limit(1).sum("extra")
    assert await sum_extra == 1


@pytest.mark.asyncio
@require_db
async def test_queryset_rename_field():
    await Book.objects.create(name="test", pages=42, volume=1)
    # ofc here we can't reload the book anymore since the field has been
    # renamed, the point is to try to rename a field into an other in the optic
    # of a migration process.
    await Book.objects.rename({"name": "title"})
    assert await Book.objects.filter(title="test").exists()
    assert not await Book.objects.filter(name="test").exists()


@pytest.mark.asyncio
@require_db
async def test():
    from motorized.queryset import QuerySet

    await Book(name="test", pages=0, volume=1).save()

    async for book in Book.objects:
        print(book)

    q = QuerySet(Book)
    x = await q.first()

    books = await Book.objects.all()
    books = await QuerySet(Book).all()
    books = await QuerySet[Book](Book).all()
