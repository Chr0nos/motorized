from motorized import Document, Field
from typing import List, Optional
from datetime import datetime


class Animal(Document):
    name: str
    legs: int = Field(default=4, ge=0, lt=5)
    is_god: bool = Field(default=False, read_only=True)
    tags: Optional[List[str]] = None
    # this will not be exposed trought the api since the field is private
    internal_comment: Optional[str] = Field(default=None, private=True)
    created: datetime = Field(default_factory=datetime.utcnow, read_only=True)
