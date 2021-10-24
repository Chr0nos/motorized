from typing import List, Any, Dict
from motorized.keywords import (
    Eq, Neq, In, Nin, Gte, Lte, Gt, Lt, Exists, Regex
)
from motorized.utils import merge_values, dict_deep_update


KEYWORDS = {
    'eq': Eq,
    'neq': Neq,
    'in': In,
    'nin': Nin,
    'gte': Gte,
    'lte': Lte,
    'gt': Gt,
    'lt': Lt,
    'exists': Exists,
    'regex': Regex
}


class Q:
    def __init__(self, **kwargs) -> None:
        self.query = self.convert_kwargs_to_query(**kwargs)

    def __repr__(self):
        return f'<Q: {self.query}>'

    def copy(self):
        instance = Q()
        instance.query = self.query.copy()
        return instance

    @classmethod
    def raw(cls, query: Dict) -> "Q":
        if not isinstance(query, dict):
            raise TypeError(f'A dictionary was expected, got {type(query)}')
        instance = cls()
        instance.query = query
        return instance

    @classmethod
    def convert_kwargs_to_query(cls, invert=False, **kwargs) -> Dict:
        query = {}
        for key, value in kwargs.items():
            path, value = cls.apply_keywords(
                value,
                key.split('__'),
                invert=invert
            )
            filter_dict = cls.dict_path(path, value)
            dict_deep_update(query, filter_dict,
                             on_conflict=merge_values)
        return query

    @staticmethod
    def read_dict_path(data: dict, path: List['str']) -> Any:
        x = data
        for node in path:
            x = x[node]
        return x

    @staticmethod
    def dict_path(path: List[str], value: Any = None) -> Dict:
        """Construct a dictionary from a path to hold the given value,
        example:
        d = QuerySet.dict_path(['a', 'b', 'c'], 42)
        d == {'a': {'b': {'c': 42}}}
        """
        out = {}
        node = out
        last_node = None
        last_key = None
        for k in path:
            node[k] = {}
            last_node = node
            node = node[k]
            last_key = k
        last_node[last_key] = value
        return out

    @classmethod
    def apply_keywords(cls, raw_value, path: List[str], invert=False):
        if invert and path[-1] not in KEYWORDS:
            path.append('eq')

        for cmd in path:
            try:
                op = KEYWORDS[cmd](raw_value)
                return path[0:-1], op.as_mongo_expression(invert)
            except KeyError:
                pass
        return path, raw_value

    def __add__(self, other: "Q") -> "Q":
        instance = self.copy()
        dict_deep_update(instance.query, other.query, on_conflict=merge_values)
        return instance

    def is_empty(self) -> bool:
        return not self.query

    def __eq__(self, other: "Q") -> bool:
        return self.query == other.query
