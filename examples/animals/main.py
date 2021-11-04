from fastapi import FastAPI
from motorized import connection

from views import router

app = FastAPI()
app.include_router(router, prefix='/api')


@app.on_event('startup')
async def startup():
    await connection.connect('mongodb://192.168.1.12:27017/test')


@app.on_event('shutdown')
async def shutdown():
    await connection.disconnect()
