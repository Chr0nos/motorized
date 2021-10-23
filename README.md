# Motorized
An ODM based on pydantic and motor

- https://motor.readthedocs.io/en/stable/api-tornado/index.html
- https://pydantic-docs.helpmanual.io/

It's build to work with asyncio to have a non-io-blocking interface to a mongodb / documentdb database and to be fully modular to let developpers customize it.

## Document
A `Document` is a pydantic `BaseModel` with saving and queryset capabilities, this mean you can define a `class Config` inside it to tweek the validation like:


### Simple document
```python
import ascynio
from typying import Literal
from motorized import Document, connection


class Book(Document):
    name: str
    volume: int
    status: Literal["NotRead", "Reading", "Read"] = "NotRead"


async def main():
    await connection.connect("mongodb://127.0.0.1:27017/test")
    # create a new book
    book = Book(name='Lord of the ring', volume=1)

    # save it to the database, you will receive a `InsertOneResult` instance
    await book.save()

    # check it is present in the db
    await Book.objects.count()

    # see all the books presents
    await book.objects.all_list()

    # update the book
    book.status = 'Reading'

    # or from a dictionary
    book.update({'status': 'NotRead'})

    # update the book from the database, this time you will have a `UpdateResult` from motor
    await book.save()

    # let's create a copy of the book now
    book.id = None
    book.volume = 2

    # since you have unset the `id` field, you will have a `InsertOneResult` with a new document id
    await book.save()

    # get all the uniques book names
    await Book.objects.distinct('name')
    # > ['Lord of the ring']

    # if you create an other book
    await Book.objects.create(name="La forteresse du chaudron noir", volume=1)

    # and now use a distinct again
    await Book.objects.distinct('name')
    # > ['Lord of the ring', 'La forteresse du chaudron noir']
```

### A bit more advanced

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
- _create_in_db
- _transform
- _update_in_db
- commit
- delete
- fetch
- get_query
- reload
- save
- update
- to_mongo

### Restriction
There is a technical restriction to be able to use ANY `Document`: having a `_id` field in the database, this is the only proper way that the ODM has to clearly identity a document without risking collisions.
This field is present in any Document by default.

## Document Methods
### get_query
This method allow you to retrive a `Q()` instance to match the current object

### save
Save the current instance into the database, if there is no `id` then the object will be inserted, otherwise this will be an update

### commit
Same as .save but the method return the instance itself instead of the result from the database

### delete
Delete the current instance from the database and set the .id attribute to None on the current instance

### _create_in_db
This method is called for new insertions in the database by the save method

### _update_in_db
This method is called to save the update in the database by the save method if the object has a .id wich is not None

### fetch
Return a fresh instance of the current instance from the database

### _transform
This method is called before the __init__ method of the pydantic `BaseModel` class and reveive the kwargs, this allow you to change fields name or add/remove fields.

The call is perform just after the fetch from the database

### Update
This method allow you to update the model with a given dictionary, the dictionary has to pass throught the validation process of pydantic, the function update and return the instance itself.
```python
class User(Document):
    name: str
    age: int


bill = User.objects.get(name="bill")
bill.update({"age": 42})
print(bill.age)
# show 42
```

## Examples
### Connect / Disconnect
```python
from motorized.client import connection

async def main():
    await connection.connect('mongodb://192.168.1.12:27017/test', connect=True)
    # here goes your interactions with the ODM
    await connection.disconnect()
```

### Add extra fields not for database saving
To achieve something like adding a field but not having it into the db, you can define a new class into your document like bellow:
```python
class Foo(Document):
    bar: bool = True
    not_in_db: str = 'this will not be saved in mongo'

    class Mongo:
        local_fields = ('not_in_db',)
```

It's also possible to declare private fields, the privates fields will not be saved in the database or be checked by pydantic (wich allow you to set private and local variables in there)
```python
class Scrapper(Document):
    url: str
    # this will not be saved in the database because it's name starts with _
    # to read/write a _ field from the database you must use an Field(alias=_name)
    # please not that you HAVE to set a value to it orherwise it won't exist in the model.
    # the type hint is purely optional and will be ignored
    _page_source: Optional[str] = None
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


### Mix differents documents in the same collection
Sometime, you want to have multiples documents who live in the same collection because they have things in common, it's possible with motorized

```python
from motorized import Document, Q


class Vehicule(Document):
    name: str
    brand: str
    seats: int
    kind: Literal["vehicule"] = "vehicule"

    class Mongo:
        collection = 'vehicules'
        # here note that we don't define the kind, so if you ask for a vehicule you will
        # also get the planes and the cars


class Plane(Vehicule):
    airport_origin: int
    airport_destination: int
    kind: Literal["plane"] = "plane"

    class Mongo:
        collection = 'vehicules'
        filters = Q(kind='plane')


class Car(Vehicule):
    weels: int
    kind: Literal["car"] = "car"

    class Mongo:
        collection = 'vehicules'
        filters = Q(kind='car')

```

here all the 3 classes are stored in the same collection but their default query will be populated by `filters` value, here we base the selection on the `kind` attribute