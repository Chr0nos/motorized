from motorized.migration import Migration

import pytest
from mock import patch, MagicMock, AsyncMock
from tests.utils import require_db


@pytest.mark.asyncio
@require_db
@patch("motorized.migration.import_module")
@patch("motorized.migration.MigrationManager.discover", return_value=["2021011200"])
async def test_pending(mock_discover, mock_import_module):
    fake_migration = MagicMock()
    fake_migration.description = 'A test migration'
    fake_migration.apply = AsyncMock(return_value=42)
    fake_migration.revert = AsyncMock(return_value=30)

    mock_import_module.return_value = fake_migration
    folder = '/test/migrations'
    pendings = await Migration.objects.pending(folder)
    mock_discover.assert_called_once_with(folder)
    assert pendings == [Migration(module_name='2021011200')]
    assert pendings != [Migration(module_name='2021011201')]

    modified_count = await Migration.objects.migrate(folder)
    assert modified_count == 42
    fake_migration.apply.assert_awaited_once()

    assert await Migration.objects.pending(folder) == []
    assert await Migration.objects.filter(module_name='2021011200').exists()

    migration = await Migration.objects.get(module_name='2021011200')
    assert await migration.revert() == 30
    fake_migration.revert.assert_awaited_once()

    # since this migration as already been applied it should be possible to
    # revert it anymore.
    with pytest.raises(ValueError):
        await migration.revert()
