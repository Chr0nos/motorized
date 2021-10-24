from typing import Optional
from motorized import Document


class Book(Document):
    name: str
    saga: Optional[str] = None
    pages: int
    volume: int
