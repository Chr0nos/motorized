from fastapi import FastAPI, status

from typing import List, Optional
from pydantic import BaseModel, Field
from motorized import Document, connection
from motorized.types import InputObjectId
from datetime import datetime


app = FastAPI()


@app.on_event('startup')
async def setup_app():
    await connection.connect('mongodb://192.168.1.12:27017/test')


@app.on_event('shutdown')
async def close_app():
    await connection.disconnect()


class BookInput(BaseModel):
    """This model contains only the fields writable by the user
    """
    name: Optional[str]
    pages: Optional[int]
    volume: Optional[int]


class Book(Document, BookInput):
    created_at: datetime = Field(default_factory=datetime.utcnow)


@app.post('/books', response_model=Book, status_code=status.HTTP_201_CREATED)
async def create_book(book: BookInput):
    return await Book(**book.dict()).commit()


@app.get('/books', response_model=List[Book])
async def get_books():
    return await Book.objects.all()


@app.get('/books/{id}')
async def get_book(id: InputObjectId):
    return await Book.objects.get(_id=id)


@app.patch('/books/{id}')
async def update_book(id: InputObjectId, update: BookInput):
    book = await Book.objects.get(_id=id)
    book.update(update.dict(exclude_unset=True))
    await book.save()
    return book


@app.delete('/bools/{id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(id: InputObjectId):
    await Book.objects.filter(_id=id).delete()
