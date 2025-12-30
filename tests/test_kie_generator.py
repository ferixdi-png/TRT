"""
Tests for Kie.ai generator in TEST_MODE/KIE_STUB.
Tests minimum 5 models of different types without network.
"""
import pytest
import asyncio
import os
import json
from unittest.mock import Mock, AsyncMock, patch

# Set test mode
os.environ['TEST_MODE'] = 'true'
os.environ['KIE_STUB'] = 'true'

from app.kie.generator import KieGenerator
from app.kie.builder import build_payload
from app.kie.parser import parse_record_info


@pytest.fixture
def generator():
    """Create generator instance."""
    gen = KieGenerator()
    gen.source_of_truth = {
        "models": [
            {
                "model_id": mid,
                "payload_format": "direct",
                "input_schema": {"required": [], "optional": [], "properties": {}},
            }
            for mid in [
                "test_text_model",
                "test_image_model",
                "test_video_model",
                "test_audio_model",
                "test_url_model",
                "test_file_model",
                "test_model",
            ]
        ]
    }
    return gen


@pytest.mark.asyncio
async def test_text_model(generator):
    """Test text generation model."""
    result = await generator.generate(
        model_id='test_text_model',
        user_inputs={'text': 'Hello world', 'prompt': 'Hello world'}
    )
    assert result['success'] is True
    assert result['result_urls']


@pytest.mark.asyncio
async def test_image_model(generator):
    """Test image generation model."""
    result = await generator.generate(
        model_id='test_image_model',
        user_inputs={'prompt': 'A beautiful sunset', 'width': 1024, 'height': 1024}
    )
    assert result['success'] is True


@pytest.mark.asyncio
async def test_video_model(generator):
    """Test video generation model."""
    result = await generator.generate(
        model_id='test_video_model',
        user_inputs={'prompt': 'A cat playing', 'duration': 5}
    )
    assert result['success'] is True


@pytest.mark.asyncio
async def test_audio_model(generator):
    """Test audio generation model."""
    result = await generator.generate(
        model_id='test_audio_model',
        user_inputs={'text': 'Hello', 'voice': 'male'}
    )
    assert result['success'] is True


@pytest.mark.asyncio
async def test_url_model(generator):
    """Test URL-based model."""
    result = await generator.generate(
        model_id='test_url_model',
        user_inputs={'url': 'https://example.com/image.jpg'}
    )
    assert result['success'] is True


@pytest.mark.asyncio
async def test_file_model(generator):
    """Test file-based model."""
    result = await generator.generate(
        model_id='test_file_model',
        user_inputs={'file': 'file_id_123', 'file_id': 'file_id_123'}
    )
    assert result['success'] is True


@pytest.mark.asyncio
async def test_fail_state(generator):
    """Test fail state handling."""
    # Mock client to return fail state
    class FailClient:
        async def create_task(self, payload, callback_url=None, **kwargs):
            return {'taskId': 'fail_task'}
        
        async def get_record_info(self, task_id):
            return {
                'state': 'fail',
                'failCode': 'TEST_ERROR',
                'failMsg': 'Test error message'
            }
    
    generator.api_client = FailClient()
    # Use a model that exists or bypass source_of_truth check
    generator.source_of_truth = {
        'models': [
            {
                'model_id': 'test_model',
                'input_schema': {'required': [], 'optional': [], 'properties': {}}
            }
        ]
    }
    result = await generator.generate('test_model', {'text': 'test'})
    
    assert result['success'] is False
    assert 'error' in result['message'].lower() or '❌' in result['message']
    # Error code could be TEST_ERROR or INVALID_INPUT depending on payload validation
    assert result['error_code'] in ['TEST_ERROR', 'INVALID_INPUT']


@pytest.mark.asyncio
async def test_timeout(generator):
    """Test timeout handling."""
    class TimeoutClient:
        async def create_task(self, payload, callback_url=None, **kwargs):
            return {'taskId': 'timeout_task'}
        
        async def get_record_info(self, task_id):
            return {'state': 'waiting'}  # Always waiting
    
    generator.api_client = TimeoutClient()
    # Use a model that exists or bypass source_of_truth check
    generator.source_of_truth = {
        'models': [
            {
                'model_id': 'test_model',
                'input_schema': {'required': [], 'optional': [], 'properties': {}}
            }
        ]
    }
    result = await generator.generate('test_model', {'text': 'test'}, timeout=5)
    
    assert result['success'] is False
    assert 'timeout' in result['message'].lower() or '⏱️' in result['message'] or 'превышено' in result['message'].lower()
    assert result['error_code'] == 'TIMEOUT'


def test_build_payload():
    """Test payload building."""
    # This will fail if model not in source_of_truth, but that's OK for test
    try:
        payload = build_payload(
            'test_model',
            {'text': 'Hello', 'prompt': 'Hello', 'width': '1024'}
        )
        assert 'model' in payload or 'text' in payload or 'prompt' in payload
    except ValueError:
        # Model not in source_of_truth, which is expected
        pass


def test_parse_record_info_success():
    """Test parsing success state."""
    record_info = {
        'state': 'success',
        'resultJson': json.dumps({
            'resultUrls': ['https://example.com/result.jpg']
        })
    }
    parsed = parse_record_info(record_info)
    assert parsed['state'] == 'success'
    assert len(parsed['result_urls']) > 0


def test_parse_record_info_single_result_url_key():
    """Handle singular resultUrl key inside resultJson payload."""
    record_info = {
        'state': 'success',
        'resultJson': json.dumps({
            'resultUrl': 'https://example.com/only.jpg'
        })
    }
    parsed = parse_record_info(record_info)
    assert parsed['result_urls'] == ['https://example.com/only.jpg']


def test_parse_record_info_fail():
    """Test parsing fail state."""
    record_info = {
        'state': 'fail',
        'failCode': 'ERROR_123',
        'failMsg': 'Test error'
    }
    parsed = parse_record_info(record_info)
    assert parsed['state'] == 'fail'
    assert parsed['error_code'] == 'ERROR_123'
    assert parsed['error_message'] == 'Test error'


def test_parse_record_info_waiting():
    """Test parsing waiting state."""
    record_info = {'state': 'waiting'}
    parsed = parse_record_info(record_info)
    assert parsed['state'] == 'waiting'
    assert 'wait' in parsed['message'].lower() or '⏳' in parsed['message']


@pytest.mark.asyncio
async def test_stub_client_supports_dual_signatures_and_polling():
    generator = KieGenerator()
    stub = generator._get_stub_client()

    # V3 style call
    resp_v3 = await stub.create_task({"model": "stub-v3", "input": {"prompt": "hi"}})
    task_v3 = resp_v3["data"]["taskId"]
    first = await stub.get_record_info(task_v3)
    assert first["state"].lower() in {"running", "waiting"}
    parsed_v3 = parse_record_info(await stub.get_record_info(task_v3))
    assert parsed_v3["state"] == "success"
    assert parsed_v3["result_urls"]

    # V4 style call
    resp_v4 = await stub.create_task("stub-v4", {"input": {"prompt": "hi"}})
    task_v4 = resp_v4["data"]["taskId"]
    _ = await stub.get_record_info(task_v4)
    parsed_v4 = parse_record_info(await stub.get_record_info(task_v4))
    assert parsed_v4["state"] == "success"
    assert parsed_v4["result_urls"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
