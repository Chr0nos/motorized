from motorized.migration import Migration

import pytest
from bson import ObjectId
from mock import patch
from datetime import datetime


@pytest.mark.asyncio
@patch("motorized.migration.import_module")
async def test_migration_without_revert(mock_import_module):
    mock_import_module.return_value = object()
    migration = Migration(module_name='test', _id=ObjectId(), applied_at=datetime.utcnow())
    assert await migration.is_applied()
    with pytest.raises(ValueError):
        await migration.revert()
