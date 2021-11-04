from pydantic import BaseModel
from typing import Any, MutableMapping, Callable, Dict, Optional


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
    if not isinstance(target, dict) and not key.startswith('$'):
        target = {'$eq': target}
    for s in sources:
        if isinstance(s, MutableMapping):
            target.update(s)
    return target


def dict_deep_update(target: MutableMapping,
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
        if isinstance(val, MutableMapping) and \
                all(isinstance(e, MutableMapping) for e in src_values):
            target[k] = dict_deep_update(val, *src_values,
                                         on_conflict=on_conflict)
        else:
            target[k] = on_conflict(k, val, *src_values)
    return target


def deep_update_model(
        model: BaseModel,
        data: Optional[Dict],
        reset_with_none: bool = True
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
