from datetime import datetime

from pydantic import BaseModel
from pydantic_partial import PartialModelMixin

from motorized import Document, Field


# the writer class is the one that the user can interract with.
class AnimalWriter(PartialModelMixin, BaseModel):
    name: str
    legs: int = Field(ge=0, lt=5)


# the reader class is the one with what the user can read.
class AnimalReader(Document, AnimalWriter):
    tags: list[str] | None = None
    created: datetime = Field(default_factory=datetime.utcnow)


# this one container read + write + all private attributes
class Animal(AnimalReader):
    internal_comment: str | None = Field(default=None)
    is_god: bool = Field(default=False)
