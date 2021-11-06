from motorized.utils import dynamic_model_node_factory, model_map
from pydantic import BaseModel
from pydantic.fields import ModelField
from typing import Optional
from bson import ObjectId

from models import Player



def test_model_build():
    def field_filtering(model: BaseModel, field: ModelField) -> Optional[ModelField]:
        return field if not field.field_info.extra.get('private') else None

    public_model = model_map(Player, field_filtering, dynamic_model_node_factory)
    assert 'id' in public_model.__fields__
    assert 'comment' not in public_model.__fields__
    the_id = ObjectId()
    input_data = {
        '_id': the_id,
        'name': 'billy',
        'golds': 42,
        'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
        'hp': {'left': 42, 'max': 100},
    }
    instance = public_model(**input_data, ignoreme=True, comment="Hide me !")
    output = instance.dict()
    output['_id'] = output.pop('id')
    assert output == input_data
