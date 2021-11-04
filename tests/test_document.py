import pytest
from bson import ObjectId
from pymongo.results import InsertOneResult, UpdateResult

from tests.models import Named
from tests.utils import require_db

from motorized.exceptions import DocumentNotSavedError


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
