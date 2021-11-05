from fastapi.routing import APIRouter
from motorized.contrib.fastapi import GenericApiView

from models import Animal


class MyView(GenericApiView):
    queryset = Animal.objects


router = APIRouter(prefix='/animals')
view = MyView()
view.register(router)
