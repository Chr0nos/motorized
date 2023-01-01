from examples.user.models import User


# this depends_on is not mandatory
depends_on = []


async def apply() -> int:
    await User.objects.create(name='root', is_admin=True)
    return 1


async def revert() -> int:
    await User.objects.filter(name='root').delete()
    return 1
