from fastapi import status
from fastapi.routing import APIRouter

from pydantic import BaseModel
from motorized import QuerySet, Document
from typing import Type, Literal, Any


Action = Literal["create", "list", "delete", "patch", "put", "retrive"]


class RestApiView:
    queryset: QuerySet
    actions = [
        ('create', '', 'POST', status.HTTP_201_CREATED),
        ('list', '', 'GET', status.HTTP_200_OK),
        ('retrieve', '/{id}', 'GET', status.HTTP_200_OK),
        ('delete', '/{id}', 'DELETE', status.HTTP_204_NO_CONTENT),
        ('patch', '/{id}', 'PATCH', status.HTTP_200_OK),
        ('put', '/{id}', 'PATCH', status.HTTP_200_OK),
    ]

    @property
    def model(self) -> Type[Document]:
        return self.queryset.model

    def register(self, router: APIRouter) -> None:

        for action, path, method, status_code in self.actions:
            if not self.is_implemented(action):
                continue
            router.add_api_route(
                path=path,
                endpoint=getattr(self, action),
                response_model=self.get_response_model(action),
                methods=[method],
                status_code=status_code,
            )

    def get_response_model(self, action: Action) -> Type[BaseModel]:
        try:
            return getattr(self, action).__annotations__['return']
        except KeyError:
            return Any

    def is_implemented(self, action: Action) -> bool:
        try:
            return callable(getattr(self, action))
        except AttributeError:
            return False
