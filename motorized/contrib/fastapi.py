from functools import wraps
from fastapi import status, Query
from fastapi.routing import APIRouter
from fastapi.exceptions import HTTPException

from pydantic import BaseModel
from pydantic.types import NonNegativeInt
from motorized import QuerySet, Document
from motorized.types import InputObjectId
from typing import (
    Type, Literal, List, Optional, Tuple, Callable
)


Action = Literal["create", "list", "delete", "patch", "put", "retrive"]
Method = Literal["GET", "POST", "DELETE", "OPTIONS", "PATCH", "PUT"]


def action(
    path: str,
    method: Method = 'GET',
    status_code: int = status.HTTP_200_OK,
    many=False,
    priority=0
):
    """Register the given function to the availables actions for this view

    Note this decorator only works for `async` views

    `Many` param will only be used if the annoation return is missing in
    addition with the View.get_response_model function
    """
    def decorator(func):
        func._is_action = True
        func._many = many
        func._priority = priority
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
    # will be used in last resort when resolving return type of an action.
    default_response_model: BaseModel = None
    router: APIRouter
    orderings: List[str] = None

    def __init__(self, router: APIRouter):
        if not hasattr(self, 'queryset'):
            raise ValueError('You MUST define a queryset attribute for views')
        self.router = router
        # populate public ordering if not set.
        if self.orderings is None:
            self.orderings = self.model.get_public_ordering_fields()

        # by default the response model is a model who include all fields
        # except the private ones.
        if not self.default_response_model:
            self.default_response_model = self.model.get_reader_model()
        self._patch_annotations()

    @property
    def model(self) -> Type[Document]:
        return self.queryset.model

    def get_actions_methods(self) -> List[Tuple[str, Callable]]:
        actions_tuples = list([
            (method_name, getattr(self, method_name))
            for method_name in dir(self)
            if self.is_action(method_name)
        ])
        actions_tuples.sort(key=lambda item: item[1]._priority, reverse=True)
        return actions_tuples

    def is_action(self, method_name: str) -> bool:
        try:
            return getattr(self, method_name)._is_action is True
        except AttributeError:
            return False

    def register(self) -> None:
        for method_name, method in self.get_actions_methods():
            params = method._router_params

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

        note the prefered way is declaring the annotaion for return of the
        function that you are implementing.
        """
        try:
            return getattr(self, action).__annotations__['return']
        except KeyError:
            if action == 'delete':
                return None
            return self.default_response_model

    def is_implemented(self, action: Action) -> bool:
        try:
            return callable(getattr(self, action))
        except AttributeError:
            return False

    def _patch_annotations(self):
        self.list.__annotations__.update({
            'order_by': Optional[List[self.orderings]],
        })
        updater = self.model.get_updater_model()
        # set the `payload` parameter type
        for action in ('create', 'patch'):
            if not hasattr(self, action):
                continue
            annotations = getattr(self, action).__annotations__
            annotations.setdefault('payload', updater)


class ReadOnlyApiViewSet(RestApiView):
    """Only allow get methods on /resource and /resource/id
    """
    @action('', 'GET', many=True)
    async def list(
        self,
        order_by = Query(None),
        skip: Optional[NonNegativeInt] = Query(None),
        limit: Optional[NonNegativeInt] = Query(10, minimum=1, maximum=50)
    ):
        return await self.queryset.order_by(order_by).skip(skip) \
            .limit(limit).all()

    @action('/{id}', 'GET', priority=-1)
    async def retrieve(self, id: InputObjectId):
        try:
            return await self.queryset.get(_id=id)
        except self.model.DocumentNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


class GenericApiView(ReadOnlyApiViewSet):
    @action('', 'POST', status.HTTP_201_CREATED)
    async def create(self, payload):
        instance = self.model(**payload.dict())
        return await instance.commit()

    @action('/{id}', 'DELETE', priority=-1)
    async def delete(self, id: InputObjectId):
        await self.queryset.filter(_id=id).delete()

    @action('/{id}', 'PATCH', priority=-1)
    async def patch(self, id: InputObjectId, payload):
        try:
            instance = await self.queryset.get(_id=id)
            instance.deep_update(payload.dict(exclude_unset=True))
            await instance.save()
            return instance
        except self.model.DocumentNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
