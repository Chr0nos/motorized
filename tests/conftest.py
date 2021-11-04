import pytest


@pytest.fixture
def database_uri() -> str:
    return 'mongodb://192.168.1.12:27017/dontuse'
