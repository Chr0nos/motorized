from motorized import Document, Field
from typing import List, Optional


class Animal(Document):
    name: str
    legs: int = Field(default=4, ge=0, lt=5)
    is_god: bool = Field(default=False, read_only=True)
    tags: Optional[List[str]] = None


AnimalUpdater = Animal.get_updater_model()
