from typing import Optional
from pydantic import BaseModel, Field
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

# - Player nested models

class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class PlayerStat(BaseModel):
    left: int
    max: int


class Player(Document):
    name: str = Field("Player one", read_only=True)
    position: Position = Position()
    golds: int = Field(read_only=True, default=0)
    hp: PlayerStat = Field(PlayerStat(left=10, max=10), read_only=True)
