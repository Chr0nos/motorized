from motorized.document import Document
from pydantic import BaseModel

def test_document_type():
    class User(Document):
        pass

    x = User()
    assert isinstance(x, BaseModel)


def test_collection_resolver_basic():
    class User(Document):
        pass

    assert User.Mongo.collection == 'users'


def test_collection_resolver_nested():
    class User(Document):
        pass

    class Student(User):
        pass

    assert Student.Mongo.collection == 'students'


def test_collection_forcing():
    class User(Document):
        class Mongo:
            collection = 'forced'

    class Student(User):
        pass

    class Alumni(Student):
        class Mongo:
            collection = 'ancients'

    assert User.Mongo.collection == 'forced'
    assert Student.Mongo.collection == 'students'
    assert Alumni.Mongo.collection == 'ancients'
