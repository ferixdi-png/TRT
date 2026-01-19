import pytest

import bot_kie
from app.kie_catalog import get_model_map


@pytest.mark.parametrize("model_id", sorted(get_model_map().keys()))
def test_select_model_param_order_covers_schema(model_id):
    spec = get_model_map()[model_id]
    param_order = bot_kie._build_param_order(spec.schema_properties)
    assert set(param_order) == set(spec.schema_properties.keys())


@pytest.mark.parametrize("model_id", sorted(get_model_map().keys()))
def test_start_next_parameter_contract(model_id):
    spec = get_model_map()[model_id]
    session = {
        "properties": spec.schema_properties,
        "params": {},
        "required": spec.schema_required,
    }
    next_param = bot_kie._select_next_param(session)
    assert next_param is not None, f"{model_id} has no next param"
    assert next_param["param_name"] in spec.schema_properties

    required_media = [
        name for name in spec.schema_required if bot_kie._get_media_kind(name)
    ]
    if required_media:
        assert next_param["media_kind"], f"{model_id} should request media first"
    else:
        assert next_param["param_name"] in {"prompt", "text"} or next_param["media_kind"] is None
