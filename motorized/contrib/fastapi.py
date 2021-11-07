from functools import wraps
from fastapi import status, Query
from fastapi.routing import APIRouter
from fastapi.exceptions import HTTPException

from pydantic import BaseModel
from pydantic.types import NonNegativeInt
from motorized import QuerySet, Document
from motorized.types import InputObjectId
from typing import Type, Literal, Any, List, Optional


Action = Literal["create", "list", "delete", "patch", "put", "retrive"]
Method = Literal["GET", "POST", "DELETE", "OPTIONS", "PATCH", "PUT"]


def action(
    path: str,
    method: Method = 'GET',
    status_code: int = status.HTTP_200_OK,
    many=False
):
    """Register the given function to the availables actions for this view

    Note this decorator only works for `async` views

    `Many` param will only be used if the annoation return is missing in
    addition with the View.get_response_model function
    """
    def decorator(func):
        func._is_action = True
        func._many = many
        # thoses parameters will be passed directly to the APIRouter
        func._router_params = {
            'path': path,
            'methods': [method],
            'status_code': status_code,
        }
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class RestApiView:
    queryset: QuerySet
    response_model: BaseModel
    router: APIRouter

    actions = [
        ('create', '', 'POST', status.HTTP_201_CREATED),
        ('list', '', 'GET', status.HTTP_200_OK),
        ('retrieve', '/{id}', 'GET', status.HTTP_200_OK),
        ('delete', '/{id}', 'DELETE', status.HTTP_204_NO_CONTENT),
        ('patch', '/{id}', 'PATCH', status.HTTP_200_OK),
        ('put', '/{id}', 'PATCH', status.HTTP_200_OK),
    ]

    def __init__(self, router: APIRouter):
        self.router = router

    @property
    def model(self) -> Type[Document]:
        return self.queryset.model

    def register(self) -> None:
        self.register_actions_methods()
        for action, path, method, status_code in self.actions:
            if not self.is_implemented(action):
                continue
            self.router.add_api_route(
                path=path,
                endpoint=getattr(self, action),
                response_model=self.get_response_model(action),
                methods=[method],
                status_code=status_code,
            )

    @property
    def actions_methods(self):
        for attribute in dir(self):
            method = getattr(self, attribute)
            try:
                if not method._is_action:
                    continue
            except AttributeError:
                continue
            yield (attribute, method)

    def register_actions_methods(self) -> None:
        for method_name, method in self.actions_methods:
            params = method._router_params
            # register the new action in the model actions.
            self.actions.append((
                method_name,
                params['path'],
                params['methods'][0],
                params['status_code'])
            )

            # resolve the response model to use.
            try:
                response_model = method.__annotations__['return']
            except KeyError:
                response_model = self.get_response_model(method_name)
                if method._many:
                    response_model = List[response_model]

            self.router.add_api_route(
                **params,
                endpoint=method,
                response_model=response_model
            )

    def get_response_model(self, action: Action) -> Type[BaseModel]:
        """Returns response model for the given action,
        you can override this method if you create new actions or if you want
        to customise the response model (ex: hide fields to user)
        """
        try:
            return getattr(self, action).__annotations__['return']
        except KeyError:
            if action == 'list':
                return List[self.response_model]
            if action == 'delete':
                return None
            return self.response_model

    def is_implemented(self, action: Action) -> bool:
        try:
            return callable(getattr(self, action))
        except AttributeError:
            return False


class GenericApiView(RestApiView):
    response_model = None

    def __init__(self, router: APIRouter):
        super().__init__(router)
        if not self.response_model:
            self.response_model = self.model.get_reader_model()
        self.orderings = self.model.get_public_ordering_fields()
        self._patch_annotations()

    def _patch_annotations(self):
        self.list.__annotations__.update({
            'order_by': Optional[List[self.orderings]],
        })
        updater = self.model.get_updater_model()
        # set the `payload` parameter type
        for action in ('create', 'patch'):
            annotations = getattr(self, action).__annotations__
            annotations.setdefault('payload', updater)

    async def create(self, payload):
        instance = self.model(**payload.dict())
        return await instance.commit()

    async def list(
        self,
        order_by = Query(None),
        skip: Optional[NonNegativeInt] = Query(None),
        limit: Optional[NonNegativeInt] = Query(10, maximum=50)
    ):
        return await self.queryset.order_by(order_by).skip(skip).limit(limit).all()

    async def retrieve(self, id: InputObjectId):
        try:
            return await self.queryset.get(_id=id)
        except self.model.DocumentNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    async def delete(self, id: InputObjectId):
        await self.queryset.filter(_id=id).delete()

    async def patch(self, id: InputObjectId, payload):
        try:
            instance = await self.queryset.get(_id=id)
            instance.deep_update(payload.dict(exclude_unset=True))
            await instance.save()
            return instance
        except self.model.DocumentNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
