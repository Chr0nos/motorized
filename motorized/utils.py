from typing import Any, MutableMapping, Callable


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
