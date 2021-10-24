from typing import Optional
from motorized import Document


class Book(Document):
    name: str
    saga: Optional[str] = None
    pages: int
    volume: int


class Named(Document):
    name: str

    def __str__(self):
        return self.name
