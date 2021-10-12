# Motorized
An ODM based on pydantic and motor

- https://motor.readthedocs.io/en/stable/api-tornado/index.html
- https://pydantic-docs.helpmanual.io/

## Document
A `Document` is a pydantic `BaseModel` with saving and queryset capabilities, this mean you can define a `class Config` inside it to tweek the validation like:

```python
class Toon(Document):
    name: str
    created: datetime
    last_fetch: datetime
    fetched: bool
    finished: bool = False
    chapter: str
    domain: str
    episode: int
    gender: str
    lang: str
    titleno: int

    class Mongo:
        collection: str = 'mongotoon'

    class Config:
        extra = 'forbid'
```

As you can see, you can also define `class Mongo` inside the document to specify the collection to use (by default: the class name in lower case + 's')

Any field or types has just to be pydantic capable definitions

# Reserved attributes names
In `Document` the following attributes names are reserved my motorized
- get_query
- save
- delete
- _create
- reload
- _transform

## Examples
### Connect / Disconnect
```python
from motorized.client import connection

async def main():
    await connection.connect('mongodb://192.168.1.12:27017/test', connect=True)

    await connection.disconnect()
```

### Save
```python
import asyncio
from motorized.client import connection
from motorized.document import Document


class User(Document):
    email: str
    has_lost_the_game: bool = True
    friends: Optional[List["User"]]


async def main():
    await connection.connect('mongodb://192.168.1.12:27017/test', connect=True)

    seb = User(email='snicolet@student.42.fr', has_lost_the_game=False)
    antoine = User(email='antoine@thegame.com')
    antoine.friends = [seb]
    await antoine.save()

    await connection.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
```
To know if a document already in the database, the ODM look up in the `id` field in the model instance, if you set it to None then if you try to save it you will create a new copy of this document in the database

### Count
```python
await User.objects.count()
```

### Distinct
Let say you want all uniques email values from your users:
```python
await User.objects.distinct('email', flat=True)
```
