# Motorized
An ODM based on pydantic and motor

- https://motor.readthedocs.io/en/stable/api-tornado/index.html
- https://pydantic-docs.helpmanual.io/

It's build to work with asyncio to have a non-io-blocking interface to a mongodb / documentdb database and to be fully modular to let developpers customize it.

## Getting started
```shell
pip install motorized
```
or if you are using poetry

```shell
poetry add motorized
```

## Scementic organisation
There is basicaly 3 main classes that you will use with motorized:
- Q
- Document
- QuerySet

Each of them has it's own purpose, when the `Document` describe ONE row of your datas, the `Q` object is a conviniance class to write mongodb queries, it does not perform any verification it just format, then the `QuerySet` is the manager of a `Document` class.

A `Q` object has absolutlely no relation with any `Document` or `QuerySet`, it's just the query object.
The `QuerySet` known of wich model it will work and manipulate the collection and set of `Document`
The `Document` validate input/output data and their insertion/update in the database.

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
    await book.objects.all()

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


if __name__ = "__main__":
    asyncio.run(main())
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

As you can see, you can also define `class Mongo` inside the document to specify the collection to use (by default: the class name in lower case + 's')

Any field or types has just to be pydantic capable definitions


### Restriction
There is a technical restriction to be able to use ANY `Document`: having a `_id` field in the database, this is the only proper way that the ODM has to clearly identity a document without risking collisions.
This field is present in any Document by default.

###
Document Methods
#### get_query
This method allow you to retrive a `Q()` instance to match the current object

#### save
Save the current instance into the database, if there is no `id` then the object will be inserted, otherwise this will be an update

#### commit
Same as .save but the method return the instance itself instead of the result from the database

#### delete
Delete the current instance from the database and set the .id attribute to None on the current instance

#### _create_in_db
This method is called for new insertions in the database by the save method

#### _update_in_db
This method is called to save the update in the database by the save method if the object has a .id wich is not None

#### fetch
Return a fresh instance of the current instance from the database

#### _transform
This method is called before the __init__ method of the pydantic `BaseModel` class and reveive the kwargs, this allow you to change fields name or add/remove fields.

The call is perform just after the fetch from the database

#### Update
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


## QuerySet
You can override the default `Document.objects` class by specifing `manager_class` in the `Mongo` class from the document like:
```python
from typing import Optional
from datetime import datetime
from pydantic import Field
from motorized import Document, QuerySet


class EmployeeManager(QuerySet):
    async def last(self) -> Optional["Employee"]:
        return await self.filter(date_left__isnull=True).order_by(['-date_joined']).first()


class Employee(Document):
    date_joined: datetime = Field(default_factory=datetime.utcnow)
    date_left: Optional[datetime]

    class Mongo:
        manager_class = EmployeeManager


async def main():
    # now you can do
    last_employee = await Employee.objects.last()

```

### Collection
Since in python, we are "We are all consenting adults", motorized will not try to prevent you using the collection directly and handle the database, if you use the `collection` attribute from `QuerySet` we assume that you know what you are doing

```python
class Book(Document):
    title: str
    pages: int


# to access the collection attribute use:
Book.objects.collection

# note: you must be connected to a database before or you will have a `NotConnectedException`

# example of aggreation from collection
pipeline = ["put here your awesome pipeline"]
results = await Book.objects.collection.aggregate(pipeline)
```

Note that while acessing the `.collection` attribute, you are in charge, the query will not do anything else for you (no ordering, no filtering)

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

### Save
```python
import asyncio
from typying import List
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
from typing import Literal


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

### Inheritance
The there is main 3 classes:
- DocumentBasis : used on all documents (also embeded)
- Document : they are a root level document.
- EmbeddedDocument: They are nested documents

then we have a mixin `PrivatesAttrsMixin` wich is used to avoid saving private attributes in the database, private attributes startswith `_`.
In all cases `pydantic` will not process private attributes.


# FastAPI
Since all the models are technicaly pydantics BaseModels, this mean the complete ODM works fine out of the box with fastapi and nothing prevent you to have something like:
```python
from fastapi import FastAPI, status

from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic.types import NonNegativeInt
from motorized import Document, connection
from motorized.types import InputObjectId
from datetime import datetime


app = FastAPI()


@app.on_event('startup')
async def setup_app():
    await connection.connect('mongodb://127.0.0.1:27017/test')


@app.on_event('shutdown')
async def close_app():
    await connection.disconnect()


class BookInput(BaseModel):
    """This model contains only the fields writable by the user
    """
    name: Optional[str]
    pages: Optional[int]
    volume: Optional[int]


# Note that the order of this inheritance is important
class Book(Document, BookInput):
    created_at: datetime = Field(default_factory=datetime.utcnow)


@app.post('/books', response_model=Book, status_code=status.HTTP_201_CREATED)
async def create_book(book: BookInput):
    return await Book(**book.dict()).commit()


@app.get('/books', response_model=List[Book])
async def get_books(
    offset: Optional[NonNegativeInt] = None,
    limit: Optional[NonNegativeInt] = 10
):
    # it's ok to pass None as skip or limit here.
    return await Book.objects.skip(offset).limit(limit).all()


@app.get('/books/{id}')
async def get_book(id: InputObjectId):
    return await Book.objects.get(_id=id)


@app.patch('/books/{id}')
async def update_book(id: InputObjectId, update: BookInput):
    book = await Book.objects.get(_id=id)
    book.update(update.dict(exclude_unset=True))
    await book.save()
    return book


@app.delete('/books/{id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(id: InputObjectId):
    await Book.objects.filter(_id=id).delete()
```

## Rest API
assuming you already have the boilerplate to connect to db and setup the `app` for FastAPI you can also use the following implementation:
```python
from fastapi.routing import APIRouter
from motorized import Field, Document
from motorized.contrib.fastapi import GenericApiView, action

router = APIRouter(prefix='/books')


class Book(Document):
    name : str
    pages: int
    volume: Optional[int]
    # here the `private` will prevent the field to be readable from the user
    # using the API, the read_only prevent user to edit it but not the code
    private_notes: Optional[str] = Field(private=True, read_only=True)


class BookViewSet(GenericApiView):
    queryset = Book.objects

    @action('/custom-endpoint')
    async def custom(self):
        return Book(name='Custom', pages=42, volume=1)


view = BookViewSet(router)
view.register()
```

This will provide following endpoints:
- `GET` /books
- `POST` /books
- `GET` /books/id
- `PATCH` /books/id
- `DELETE` /books/id
- `GET` /books/id/custom-endpoint

all PATCH methods will accept partial payloads

This little conveniant class for viewset can be used without the default method by using the `RestApiView` class from the `motorized.contrib.fastapi` module.
