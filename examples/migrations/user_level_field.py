from examples.user.models import User
from motorized.migration import alter_field


depends_on = ['examples.migrations.base']


async def apply() -> int:
    """Create a new `level` field for users
    """
    # set all the users at level 0
    await User.objects.collection.update_many({}, {'$set': {'level': 0}})

    # set admins at level 1
    await User.objects.collection.update_many(
        {'is_admin': True},
        {'$set': {'level': 1}}
    )
    return await User.objects.count()


async def revert() -> int:
    return await User.objects.collection.update_many(
        {},
        {'$unset': {'level': True}}
    ).modified_count()
