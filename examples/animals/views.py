from fastapi.routing import APIRouter

from typing import List, Optional

from motorized.contrib.fastapi import RestApiView
from motorized.types import InputObjectId

from models import Animal, AnimalUpdater


class MyView(RestApiView):
    queryset = Animal.objects

    async def create(self, payload: AnimalUpdater) -> Animal:
        """Creates a new animal, this will be present in the description page
        """
        animal = Animal(**payload.dict())
        return await animal.commit()

    async def list(self) -> List[Animal]:
        return await self.queryset.all()

    async def retrieve(self, id: InputObjectId) -> Optional[Animal]:
        return await self.queryset.filter(_id=id).first()

    async def delete(self, id: InputObjectId) -> None:
        await self.queryset.filter(_id=id).delete()

    async def patch(self, id: InputObjectId, input: AnimalUpdater) -> Animal:
        animal = await self.queryset.get(_id=id)
        animal.deep_update(input.dict(exclude_unset=True))
        await animal.save()
        return animal


router = APIRouter(prefix='/animals')
view = MyView()
view.register(router)
