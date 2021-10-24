from typing import Optional
import pytest
from typing import Optional
from motorized import Document
from tests.utils import require_db
from tests.models import Book


@pytest.mark.asyncio
@require_db
async def test_aggregations():
    fellowship = Book(saga='lotr', name='The fellowship of the ring', pages=456, volume=1)
    king = Book(saga='lotr', name='The return of the king', pages=544, volume=3)
    await Book.objects.create(name='entropy', pages=443, volume=1)

    await fellowship.save()
    await king.save()

    assert await Book.objects.count() == 3
    assert await Book.objects.filter(saga='lotr').count() == 2
    assert await Book.objects.filter(saga='lotr').sum('pages') == 1000
    assert await Book.objects.filter(saga='lotr').avg('pages') == 500.0
