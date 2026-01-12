#!/usr/bin/env python3
"""E2E tests for ALL FREE models - CLI tool"""
import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.kie.generator import KieGenerator
from app.pricing.free_models import get_free_models
from app.utils.correlation import ensure_correlation_id, correlation_tag

logger = logging.getLogger(__name__)


def load_test_image() -> str:
    """Load 1x1 PNG base64"""
    fixture = Path(__file__).parent.parent / "tests/fixtures/test_image_1x1.txt"
    return fixture.read_text().strip()


def load_sot() -> Dict:
    """Load SOURCE_OF_TRUTH"""
    sot = Path(__file__).parent.parent / "models/KIE_SOURCE_OF_TRUTH.json"
    with open(sot, 'r') as f:
        return json.load(f)


def build_input(model_id: str, sot: Dict) -> Dict[str, Any]:
    """Build minimal input for model"""
    models = sot.get('models', {})
    model_data = models.get(model_id, {})
    schema = model_data.get('input_schema', {}).get('input', {})
    examples = schema.get('examples', [])
    
    base = examples[0].copy() if examples and isinstance(examples[0], dict) else {}
    
    if 'image-edit' in model_id or 'image-to-image' in model_id:
        return {
            'image': load_test_image(),
            'prompt': 'test котик',
            'guidance_scale': base.get('guidance_scale', 7.5),
            'num_inference_steps': base.get('num_inference_steps', 20),
            'strength': base.get('strength', 0.75)
        }
    elif 'text-to-image' in model_id:
        return {
            'prompt': 'test котик',
            'guidance_scale': base.get('guidance_scale', 7.5),
            'num_inference_steps': base.get('num_inference_steps', 20),
            'image_size': base.get('image_size', 'square')
        }
    elif model_id == 'z-image':
        return {
            'prompt': 'test котик',
            'aspect_ratio': base.get('aspect_ratio', '1:1')
        }
    else:
        return base if base else {'prompt': 'test'}


async def test_model(model_id: str, sot: Dict, timeout: int = 180) -> Dict:
    """Test single FREE model E2E"""
    corr_id = f"e2e_{model_id}_{datetime.now().strftime('%H%M%S')}"
    ensure_correlation_id(corr_id)
    start = datetime.now()
    
    try:
        inputs = build_input(model_id, sot)
        logger.info(f"{correlation_tag()} Testing {model_id}: {list(inputs.keys())}")
        
        gen = KieGenerator()
        result = await gen.generate(model_id, inputs, None, timeout)
        
        dur = (datetime.now() - start).total_seconds()
        success = result.get('success', False)
        task_id = result.get('task_id')
        urls = result.get('result_urls', [])
        
        status = 'done' if success and urls else ('timeout' if result.get('error_code') == 'TIMEOUT' else 'failed')
        
        logger.info(f"{correlation_tag()} {model_id} → {status} | {dur:.1f}s | task_id={task_id}")
        
        return {
            'model_id': model_id,
            'success': success,
            'status': status,
            'task_id': task_id,
            'correlation_id': corr_id,
            'duration': dur,
            'error': result.get('error_message') if not success else None,
            'urls': urls
        }
    except Exception as e:
        dur = (datetime.now() - start).total_seconds()
        logger.error(f"{correlation_tag()} Exception: {e}", exc_info=True)
        return {
            'model_id': model_id,
            'success': False,
            'status': 'exception',
            'task_id': None,
            'correlation_id': corr_id,
            'duration': dur,
            'error': str(e),
            'urls': []
        }


async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    is_real = os.getenv('RUN_E2E', '0') == '1'
    if not is_real:
        logger.warning("DRY RUN (set RUN_E2E=1 for real tests)")
    
    free_ids = get_free_models()
    logger.info(f"FREE models: {free_ids}")
    
    if not free_ids:
        logger.error("No FREE models!")
        sys.exit(1)
    
    sot = load_sot()
    results = []
    
    for mid in free_ids:
        logger.info(f"\n{'='*60}\n{mid}\n{'='*60}")
        r = await test_model(mid, sot, 180)
        results.append(r)
        emoji = "✅" if r['success'] else "❌"
        logger.info(f"{emoji} {mid}: {r['status']} ({r['duration']:.1f}s)")
    
    passed = sum(1 for r in results if r['success'])
    failed = len(results) - passed
    
    logger.info(f"\nSUMMARY: {passed}/{len(results)} passed, {failed} failed")
    for r in results:
        e = "✅" if r['success'] else "❌"
        logger.info(f"{e} {r['model_id']}: {r['status']} | corr_id={r['correlation_id']}")
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    asyncio.run(main())
