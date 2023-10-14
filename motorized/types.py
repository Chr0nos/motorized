from bson import ObjectId
from bson.errors import InvalidId


class PydanticObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _):
        if not isinstance(v, ObjectId):
            raise TypeError("ObjectId required")
        return v

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: dict):
        schema["type"] = "string"


class InputObjectId(str):
    """Represent a string but will be casted as an ObjectId
    this should be used when retriving an ObjectId from a user,
    ex: fastapi endpoint parameter
    """

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _):
        try:
            return ObjectId(str(v))
        except (ValueError, InvalidId):
            raise TypeError("ObjectId required")
