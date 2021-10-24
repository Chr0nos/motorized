from bson import ObjectId


class PydanticObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, ObjectId):
            raise TypeError('ObjectId required')
        return v

    @classmethod
    def __modify_schema__(cls, schema: dict):
        schema['type'] = 'string'
