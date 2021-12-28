from fastapi import Query
from fastapi.routing import APIRouter
from motorized.contrib.fastapi import GenericApiView, action
from typing import List

from models import Animal


class AnimalViewSet(GenericApiView):
    queryset = Animal.objects

    # in addition of all the REST methods, it's also possible to define extra
    @action('/by-tag', many=True)
    async def get_animals_by_tags(self, tags: List[str] = Query(...)):
        return await self.queryset.filter(tags=tags).all()


router = APIRouter(prefix='/animals')
view = AnimalViewSet(router)
view.register()
