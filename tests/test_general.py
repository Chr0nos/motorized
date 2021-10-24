import pytest
from typing import Optional
from typing import Optional
from motorized import Document
from tests.utils import require_db
from tests.models import Book


@pytest.mark.asyncio
@require_db
async def test_queryset_all():
    assert await Book.objects.all() == []

    book = await Book.objects.create(name='test', saga='test', pages=1, volume=1)
    books = await Book.objects.all()
    assert len(books) == 1
    assert isinstance(books, list)
    assert books[0] == book


@pytest.mark.asyncio
@require_db
async def test_queryset_async_iter():
    await Book.objects.create(name='test', pages=1, volume=1)
    await Book.objects.create(name='test', pages=1, volume=2)

    expected_volume = 1
    async for book in Book.objects.order_by(['volume']):
        assert isinstance(book, Book)
        assert book.volume == expected_volume
        expected_volume += 1
    assert expected_volume == 3


@pytest.mark.asyncio
@require_db
async def test_map():
    await Book.objects.create(name='test', pages=1, volume=1)
    await Book.objects.create(name='toto', pages=40, volume=2)

    async def mapping_function(book: Book) -> int:
        return book.pages * 2

    result = await Book.objects.map(mapping_function)
    assert result == [2, 80]


@pytest.mark.asyncio
@require_db
async def test_get_simple():
    await Book.objects.create(name='entropy', pages=1, volume=2)
    await Book.objects.create(name='test', pages=1, volume=4)

    book = await Book.objects.get(name='test')
    assert book.name == 'test'


@pytest.mark.asyncio
@require_db
async def test_get_too_many_results():
    await Book.objects.create(name='a', pages=1, volume=1)
    await Book.objects.create(name='a', pages=4, volume=2)
    with pytest.raises(Book.TooManyMatchException):
        await Book.objects.get(name='a')

@pytest.mark.asyncio
@require_db
async def test_commit():
    book = Book(name='test', pages=42, volume=3)
    assert await book.commit() == book
    assert book.id


@pytest.mark.asyncio
@require_db
async def test_reload():
    book = await Book.objects.create(name='test', pages=42, volume=3)
    # simulate a side effect, like an other process had changed the book
    await Book.objects.collection.update_one({'_id': book.id}, {'$set': {'volume': 1}})

    await book.reload()
    assert book.volume == 1
    assert book.name == 'test'
    assert book.pages == 42
