from typing import Type
import pytest
from motorized.query import Q


def test_from_raw():
    raw = {'_id': '1234'}
    query = Q.raw(raw)
    assert isinstance(query, Q)
    assert query.query == raw


def test_from_raw_wrong_input():
    with pytest.raises(TypeError):
        Q.raw(123)
