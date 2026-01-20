import json

from app.generations.universal_engine import parse_record_info
from app.generations import media_pipeline


def test_result_json_media_type_drives_output_method():
    record = {
        "taskId": "task-1",
        "state": "success",
        "resultJson": json.dumps(
            {
                "mediaType": "audio",
                "resultUrls": ["https://example.com/result"],
            }
        ),
    }

    result = parse_record_info(record, media_type="document", model_id="test-model")
    assert result.media_type == "audio"

    method = media_pipeline._media_method_from_type("audio", "audio/mpeg", "https://example.com/result")
    assert method == "send_audio"
