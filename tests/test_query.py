import pytest

from motorized.query import Q


def test_from_raw():
    raw = {"_id": "1234"}
    query = Q.raw(raw)
    assert isinstance(query, Q)
    assert query.query == raw


def test_from_raw_wrong_input():
    with pytest.raises(TypeError):
        Q.raw(123)


def test_emptyness():
    assert Q().is_empty()
    assert not Q(name="test").is_empty()


def test_repr():
    queries = [Q(), Q(name="test"), Q(a=1) + Q(b=2), Q.raw({"name": {"$in": ["test", "true"]}})]
    for query in queries:
        assert isinstance(query.__repr__(), str)
        assert isinstance(query.__str__(), str)


def test_copy():
    query = Q(name__in=["charles", "alice"], age__ge=18)
    assert query == query.copy()
