"""
WAN 2.6 Handlers for T2V/I2V/V2V modes.
Simple, focused handlers for KIE API integration.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from kie_client import get_client

logger = logging.getLogger(__name__)


def validate_wan_input(
    prompt: str,
    duration: Optional[str] = None,
    resolution: Optional[str] = None,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
    mode: str = "t2v"
) -> tuple[bool, Optional[str]]:
    """
    Validate WAN 2.6 input parameters.
    
    Returns:
        (is_valid, error_message)
    """
    # Prompt validation
    if not prompt or not isinstance(prompt, str):
        return False, "prompt is required and must be a string"
    
    prompt_len = len(prompt.strip())
    if prompt_len < 1 or prompt_len > 5000:
        return False, f"prompt length must be 1-5000 characters (got {prompt_len})"
    
    # Duration validation
    if duration is not None:
        valid_durations = ["5", "10", "15"]
        if mode == "v2v":
            valid_durations = ["5", "10"]  # V2V only supports 5 and 10
        if duration not in valid_durations:
            return False, f"duration must be one of {valid_durations} (got {duration})"
    
    # Resolution validation
    if resolution is not None:
        if resolution not in ["720p", "1080p"]:
            return False, f"resolution must be '720p' or '1080p' (got {resolution})"
    
    # Mode-specific validation
    if mode == "i2v":
        if not image_url:
            return False, "image_url is required for I2V mode"
        if not image_url.startswith("http"):
            return False, "image_url must start with http:// or https://"
    
    if mode == "v2v":
        if not video_url:
            return False, "video_url is required for V2V mode"
        if not video_url.startswith("http"):
            return False, "video_url must start with http:// or https://"
    
    return True, None


async def handle_wan_t2v(
    prompt: str,
    duration: Optional[str] = None,
    resolution: Optional[str] = None
) -> tuple[bool, Optional[List[str]], Optional[str]]:
    """
    Handle WAN 2.6 Text-to-Video generation.
    
    Returns:
        (success, result_urls, error_message)
    """
    # Validate input
    is_valid, error = validate_wan_input(prompt, duration, resolution, mode="t2v")
    if not is_valid:
        return False, None, error
    
    # Prepare input
    input_data = {
        "prompt": prompt.strip()
    }
    if duration:
        input_data["duration"] = duration
    if resolution:
        input_data["resolution"] = resolution
    
    # Create task
    try:
        client = get_client()
        result = await client.create_task("wan/2-6-text-to-video", input_data)
        
        if not result.get('ok'):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"event=wan.t2v.create_task status=error error={error_msg}")
            return False, None, error_msg
        
        task_id = result.get('taskId')
        logger.info(f"event=wan.t2v.create_task status=success task_id={task_id}")
        
        # Wait for completion
        final_result = await client.wait_task(task_id, timeout_s=900, poll_s=3)
        
        state = final_result.get('state')
        if state == 'success':
            # Extract resultUrls from resultJson if needed, or use direct resultUrls
            result_urls = final_result.get('resultUrls', [])
            if not result_urls and final_result.get('resultJson'):
                try:
                    result_json_str = final_result.get('resultJson')
                    if isinstance(result_json_str, str):
                        result_json = json.loads(result_json_str)
                        result_urls = result_json.get('resultUrls', [])
                except:
                    pass
            
            logger.info(f"event=wan.t2v.wait_task status=success result_urls_count={len(result_urls)}")
            return True, result_urls, None
        else:
            error_msg = final_result.get('failMsg') or final_result.get('errorMessage', 'Task failed')
            logger.error(f"event=wan.t2v.wait_task status=fail error={error_msg}")
            return False, None, error_msg
            
    except TimeoutError as e:
        logger.error(f"event=wan.t2v.wait_task status=timeout error={str(e)}")
        return False, None, f"Timeout: {str(e)}"
    except ValueError as e:
        logger.error(f"event=wan.t2v.wait_task status=error error={str(e)}")
        return False, None, str(e)
    except Exception as e:
        logger.error(f"event=wan.t2v.wait_task status=exception error={str(e)}", exc_info=True)
        return False, None, f"Unexpected error: {str(e)}"


async def handle_wan_i2v(
    prompt: str,
    image_url: str,
    duration: Optional[str] = None,
    resolution: Optional[str] = None
) -> tuple[bool, Optional[List[str]], Optional[str]]:
    """
    Handle WAN 2.6 Image-to-Video generation.
    
    Returns:
        (success, result_urls, error_message)
    """
    # Validate input
    is_valid, error = validate_wan_input(prompt, duration, resolution, image_url=image_url, mode="i2v")
    if not is_valid:
        return False, None, error
    
    # Prepare input
    input_data = {
        "prompt": prompt.strip(),
        "image_urls": [image_url]
    }
    if duration:
        input_data["duration"] = duration
    if resolution:
        input_data["resolution"] = resolution
    
    # Create task
    try:
        client = get_client()
        result = await client.create_task("wan/2-6-text-to-video", input_data)
        
        if not result.get('ok'):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"event=wan.i2v.create_task status=error error={error_msg}")
            return False, None, error_msg
        
        task_id = result.get('taskId')
        logger.info(f"event=wan.i2v.create_task status=success task_id={task_id}")
        
        # Wait for completion
        final_result = await client.wait_task(task_id, timeout_s=900, poll_s=3)
        
        state = final_result.get('state')
        if state == 'success':
            result_urls = final_result.get('resultUrls', [])
            if not result_urls and final_result.get('resultJson'):
                try:
                    result_json_str = final_result.get('resultJson')
                    if isinstance(result_json_str, str):
                        result_json = json.loads(result_json_str)
                        result_urls = result_json.get('resultUrls', [])
                except:
                    pass
            
            logger.info(f"event=wan.i2v.wait_task status=success result_urls_count={len(result_urls)}")
            return True, result_urls, None
        else:
            error_msg = final_result.get('failMsg') or final_result.get('errorMessage', 'Task failed')
            logger.error(f"event=wan.i2v.wait_task status=fail error={error_msg}")
            return False, None, error_msg
            
    except TimeoutError as e:
        logger.error(f"event=wan.i2v.wait_task status=timeout error={str(e)}")
        return False, None, f"Timeout: {str(e)}"
    except ValueError as e:
        logger.error(f"event=wan.i2v.wait_task status=error error={str(e)}")
        return False, None, str(e)
    except Exception as e:
        logger.error(f"event=wan.i2v.wait_task status=exception error={str(e)}", exc_info=True)
        return False, None, f"Unexpected error: {str(e)}"


async def handle_wan_v2v(
    prompt: str,
    video_url: str,
    duration: Optional[str] = None,
    resolution: Optional[str] = None
) -> tuple[bool, Optional[List[str]], Optional[str]]:
    """
    Handle WAN 2.6 Video-to-Video generation.
    
    Returns:
        (success, result_urls, error_message)
    """
    # Validate input
    is_valid, error = validate_wan_input(prompt, duration, resolution, video_url=video_url, mode="v2v")
    if not is_valid:
        return False, None, error
    
    # Prepare input
    input_data = {
        "prompt": prompt.strip(),
        "video_urls": [video_url]
    }
    if duration:
        input_data["duration"] = duration
    if resolution:
        input_data["resolution"] = resolution
    
    # Create task
    try:
        client = get_client()
        result = await client.create_task("wan/2-6-text-to-video", input_data)
        
        if not result.get('ok'):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"event=wan.v2v.create_task status=error error={error_msg}")
            return False, None, error_msg
        
        task_id = result.get('taskId')
        logger.info(f"event=wan.v2v.create_task status=success task_id={task_id}")
        
        # Wait for completion
        final_result = await client.wait_task(task_id, timeout_s=900, poll_s=3)
        
        state = final_result.get('state')
        if state == 'success':
            result_urls = final_result.get('resultUrls', [])
            if not result_urls and final_result.get('resultJson'):
                try:
                    result_json_str = final_result.get('resultJson')
                    if isinstance(result_json_str, str):
                        result_json = json.loads(result_json_str)
                        result_urls = result_json.get('resultUrls', [])
                except:
                    pass
            
            logger.info(f"event=wan.v2v.wait_task status=success result_urls_count={len(result_urls)}")
            return True, result_urls, None
        else:
            error_msg = final_result.get('failMsg') or final_result.get('errorMessage', 'Task failed')
            logger.error(f"event=wan.v2v.wait_task status=fail error={error_msg}")
            return False, None, error_msg
            
    except TimeoutError as e:
        logger.error(f"event=wan.v2v.wait_task status=timeout error={str(e)}")
        return False, None, f"Timeout: {str(e)}"
    except ValueError as e:
        logger.error(f"event=wan.v2v.wait_task status=error error={str(e)}")
        return False, None, str(e)
    except Exception as e:
        logger.error(f"event=wan.v2v.wait_task status=exception error={str(e)}", exc_info=True)
        return False, None, f"Unexpected error: {str(e)}"
