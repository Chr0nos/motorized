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
In `Document` the following attributes names are reserved by motorized
- _aliased_fields
- _create
- _transform
- _update
- commit
- delete
- fetch
- get_query
- save
- to_mongo

## Document Methods
### get_query
This method allow you to retrive a `Q()` instance to match the current object

### save
Save the current instance into the database, if there is no `id` then the object will be inserted, otherwise this will be an update

### commit
Same as .save but the method return the instance itself instead of the result from the database

### delete
Delete the current instance from the database and set the .id attribute to None on the current instance

### _create
This method is called for new insertions in the database by the save method

### _update
This method is called to save the update in the database by the save method if the object has a .id wich is not None

### fetch
Return a fresh instance of the current instance from the database

### _transform
This method is called before the __init__ method of the pydantic `BaseModel` class and reveive the kwargs, this allow you to change fields name or add/remove fields.

The call is perform just after the fetch from the database


## Examples
### Connect / Disconnect
```python
from motorized.client import connection

async def main():
    await connection.connect('mongodb://192.168.1.12:27017/test', connect=True)
    # here goes your interactions with the ODM
    await connection.disconnect()
```
### Embeded documents
Having nested document could not be more easy, just put a `BaseModel` from pydantic in the `Document` declaration like bellow
```python
from pydantic.main import BaseModel
from motorized.client import connection
from motorized.document import Document

class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class User(Document):
    email: str
    has_lost_the_game: bool = True
    position: Position
```
Embeded documents does not need to be `Document` because you only save the top level one.

If you want to refer the current document (like the document itself) you can:

```python
from typing import Optional, List
from motorized.document import Document

class User(Document):
    email: str
    has_lost_the_game: bool = True
    friends: Optional[List["User"]]


# you will probably have to updated the forwared reference with:
User.update_forward_refs()
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
