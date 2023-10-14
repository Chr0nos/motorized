from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo
from typing import Any, MutableMapping, Callable, Dict, Optional, List, Type, Union
from bson import ObjectId
from functools import lru_cache, partial


def take_last_value(key: str, target: Any, *sources: Any) -> Any:
    """Conflict resolver returning last source
    Args:
        target : current value
        sources : list of update values
    Returns:
        Any: the last value from sources
    """
    try:
        return sources[-1]
    except KeyError:
        return target


def take_first_value(key: str, target: Any, *sources: Any) -> Any:
    """Conflict resolver returning first source
    Args:
        target : current value
        sources : list of update values
    Returns:
        Any: the last value from sources
    """
    try:
        return sources[0]
    except KeyError:
        return target


def merge_values(key: str, target: Any, *sources: Any) -> Any:
    if not isinstance(target, dict) and not key.startswith("$"):
        target = {"$eq": target}
    for s in sources:
        if isinstance(s, MutableMapping):
            target.update(s)
    return target


def dict_deep_update(
    target: MutableMapping,
    *sources: MutableMapping,
    on_conflict: Callable[..., Any] = take_last_value,
) -> MutableMapping:
    """Update a dict with values from others
    Args:
        target : dict to update. (will be modified)
        sources : source dict(s) to update target.
        on_conflict (Callable[[target, *sources], Any], optional):
            define comportment when a key is present in the target
            and/or in multiple source. Defaults to take_last_value.
    Returns:
        MutableMapping: return target so it can be used like this :
        new_dict = dict_deep_update({"key1":"value"}, other)
    """
    merge_keys = []
    for source in sources:
        for k, val in source.items():
            if k in target:
                merge_keys.append(k)
            else:
                target[k] = val
    for k in merge_keys:
        val = target[k]
        src_values = tuple(src[k] for src in sources if k in src)
        if isinstance(val, MutableMapping) and all(
            isinstance(e, MutableMapping) for e in src_values
        ):
            target[k] = dict_deep_update(val, *src_values, on_conflict=on_conflict)
        else:
            target[k] = on_conflict(k, val, *src_values)
    return target


def deep_update_model(
    model: BaseModel, data: Optional[Dict], reset_with_none: bool = True
) -> BaseModel:
    """Update the given model with `data` paylaod (dict) merging childs
    to allow a partial update without loading default values for missing fields

    eratas: since this is a recursive function, this will not work with
    circular dependencies and can raise a RecursionError.
    """
    if data is None:
        return model
    for field, value in data.items():
        node = getattr(model, field, None)
        is_nested_document = isinstance(node, BaseModel)
        if is_nested_document:
            # if the user pass a None to a nested attribute, we want to reset
            # the node.
            if value is None and reset_with_none:
                setattr(model, field, {})
            else:
                deep_update_model(node, data[field])
        else:
            setattr(model, field, value)
    return model


def safe_issubclass(a, b) -> bool:
    try:
        return issubclass(a, b)
    except TypeError:
        return False


def get_all_fields_names(
    model: BaseModel,
    prefix: str = "",
    separator: str = "__",
    field_skip_func: Optional[Callable[[str, FieldInfo], bool]] = None,
) -> list[str]:
    fields: list[str] = []
    for field_name, field in model.model_fields.items():
        if field_skip_func and field_skip_func(field_name, field):
            continue
        if safe_issubclass(field.annotation, BaseModel):
            fields.extend(
                get_all_fields_names(
                    field.annotation,
                    f"{prefix}{field_name}{separator}",
                    separator,
                    field_skip_func=field_skip_func,
                )
            )
        else:
            fields.append(prefix + field_name)
    return fields


def get_all_fields(
    model: BaseModel,
    is_ignored: Optional[Callable[[BaseModel, FieldInfo], bool]] = None,
    node_factory: Type = dict,
) -> Dict[str, FieldInfo]:
    fields = {}
    for field_name, field in model.model_fields.items():
        if is_ignored and is_ignored(model, field):
            continue
        if safe_issubclass(field.annotation, BaseModel):
            fields[field_name] = get_all_fields(model=field.annotation, is_ignored=is_ignored)
        else:
            fields[field_name] = field
    return node_factory(fields)


def model_map(
    model: BaseModel,
    func: Callable[[BaseModel, str, FieldInfo], Optional[Any]],
    node_factory: Callable[[BaseModel, Any, bool], Optional[Any]] = lambda model, data, _: data,
    annotate_all_optional: bool = False,
):
    output = {}
    for field_name, field in model.model_fields.items():
        field = func(model, field_name, field)
        if field is None:
            continue
        if safe_issubclass(field.annotation, BaseModel):
            output[field_name] = model_map(
                field.annotation, func, node_factory, annotate_all_optional
            )
        else:
            output[field_name] = field
    return node_factory(model, output, annotate_all_optional)


@lru_cache
def partial_model(
    baseclass: Type[BaseModel],
    field_filter: Callable[[str, FieldInfo], bool] | None = None,
    suffix: str = "Partial",
) -> Type[BaseModel]:
    """Make all fields in supplied Pydantic BaseModel Optional, for use in PATCH calls.

    Iterate over fields of baseclass, descend into sub-classes, convert fields to Optional and return new model.
    Cache newly created model with lru_cache to ensure it's only created once.
    Use with Body to generate the partial model on the fly, in the PATCH path operation function.

    - https://stackoverflow.com/questions/75167317/make-pydantic-basemodel-fields-optional-including-sub-models-for-patch
    - https://stackoverflow.com/questions/67699451/make-every-fields-as-optional-with-pydantic
    - https://github.com/pydantic/pydantic/discussions/3089
    - https://fastapi.tiangolo.com/tutorial/body-updates/#partial-updates-with-patch
    """
    fields = {}
    for name, field in baseclass.model_fields.items():
        if field_filter and not field_filter(field):
            continue

        type_ = field.annotations
        if type_.__base__ is BaseModel:
            fields[name] = (Optional[partial(type_)], {})
        else:
            fields[name] = (Optional[type_], None) if field.required else (type_, field.default)
    # https://docs.pydantic.dev/usage/models/#dynamic-model-creation
    validators = {"__validators__": baseclass.__validators__}
    return create_model(baseclass.__name__ + suffix, **fields, __validators__=validators)


def field_mark_filter(mark_list: List[str], field_name: str, field: FieldInfo) -> bool:
    """Allow filtering of partial models to exclude fields by their names
    if True the field will be kept, otherwise it will be removed from the
    generated partial model.

    ex:
    ```python
    PartialModel = partial_model(partial(field_mark_filter, ['private']))
    ```
    """
    for mark in mark_list:
        if field.json_schema_extra and field.json_schema_extra.get(mark):
            return False
    return True


def partial_update(baseclass: Type[BaseModel], suffix="PartialUpdate") -> Type[BaseModel]:
    """Return a model based on baseclass to partially update it.
    all private & read_only fields will be removed.
    all remaining fields will be optional
    """
    return partial_model(
        baseclass, partial(field_mark_filter, ["private", "read_only"]), suffix=suffix
    )
