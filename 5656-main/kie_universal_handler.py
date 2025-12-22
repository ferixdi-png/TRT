"""
Universal KIE Generation Handler.

Single unified handler for all KIE AI models using the model registry
and validator. This handler:
1. Validates input against model schema
2. Creates generation task via KIE API
3. Waits for task completion
4. Parses result URLs from response
5. Returns structured result with error handling

This eliminates the need for individual handlers for each of the 72+ models.
"""

import logging
import json
from typing import Dict, Any, List, Optional, Tuple
from kie_client import get_client
from kie_validator import validate

logger = logging.getLogger(__name__)


async def handle_kie_generation(
    model_id: str,
    user_input: Dict[str, Any],
    callback_url: Optional[str] = None
) -> Tuple[bool, Optional[List[str]], Optional[str], Optional[str]]:
    """
    Universal handler for KIE generation.
    
    Args:
        model_id: Model ID (e.g., "wan/2-6-text-to-video")
        user_input: User-provided input parameters
        callback_url: Optional callback URL
    
    Returns:
        (success, result_urls, error_message, task_id)
    """
    # Validate input
    is_valid, errors = validate(model_id, user_input)
    if not is_valid:
        error_msg = "; ".join(errors)
        logger.error(f"event=kie.validate model={model_id} status=invalid errors={error_msg}")
        return False, None, error_msg, None
    
    # Create task
    try:
        client = get_client()
        result = await client.create_task(model_id, user_input, callback_url)
        
        if not result.get('ok'):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"event=kie.create_task model={model_id} status=error error={error_msg}")
            return False, None, error_msg, None
        
        task_id = result.get('taskId')
        logger.info(f"event=kie.create_task model={model_id} status=success task_id={task_id}")
        
        # Wait for completion
        final_result = await client.wait_task(task_id, timeout_s=900, poll_s=3)
        
        state = final_result.get('state')
        if state == 'success':
            # Extract resultUrls
            result_urls = final_result.get('resultUrls', [])
            
            # If no direct resultUrls, try parsing from resultJson
            if not result_urls and final_result.get('resultJson'):
                try:
                    result_json_str = final_result.get('resultJson')
                    if isinstance(result_json_str, str):
                        result_json = json.loads(result_json_str)
                        result_urls = result_json.get('resultUrls', [])
                except Exception as e:
                    logger.warning(f"event=kie.parse_result model={model_id} task_id={task_id} error={str(e)}")
            
            logger.info(f"event=kie.wait_task model={model_id} task_id={task_id} status=success result_urls_count={len(result_urls)}")
            return True, result_urls, None, task_id
        else:
            error_msg = final_result.get('failMsg') or final_result.get('errorMessage', 'Task failed')
            fail_code = final_result.get('failCode')
            if fail_code:
                error_msg = f"[{fail_code}] {error_msg}"
            logger.error(f"event=kie.wait_task model={model_id} task_id={task_id} status=fail error={error_msg}")
            return False, None, error_msg, task_id
            
    except TimeoutError as e:
        logger.error(f"event=kie.wait_task model={model_id} status=timeout error={str(e)}")
        return False, None, f"Timeout: {str(e)}", None
    except ValueError as e:
        logger.error(f"event=kie.wait_task model={model_id} status=error error={str(e)}")
        return False, None, str(e), None
    except Exception as e:
        logger.error(f"event=kie.wait_task model={model_id} status=exception error={str(e)}", exc_info=True)
        return False, None, f"Unexpected error: {str(e)}", None
