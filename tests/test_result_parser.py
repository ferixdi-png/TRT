import json
import pytest

from app.generations.universal_engine import parse_record_info, KIEResultError


def test_parse_result_object_as_text():
    record = {
        "taskId": "task-1",
        "state": "success",
        "resultJson": json.dumps({"resultObject": {"text": "hello"}}),
    }
    result = parse_record_info(record, "text", "test-model")
    assert "text" in result.text


def test_parse_empty_result_raises():
    record = {"taskId": "task-2", "state": "success", "resultJson": "{}"}
    with pytest.raises(KIEResultError):
        parse_record_info(record, "image", "test-model")
