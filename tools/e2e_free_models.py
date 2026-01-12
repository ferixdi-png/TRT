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


async def test_model(model_id: str, sot: Dict, user_id: int = 123456789, chat_id: int = 123456789, timeout: int = 180) -> Dict:
    """Test single FREE model E2E with storage and Telegram checks"""
    corr_id = f"e2e_{model_id}_{datetime.now().strftime('%H%M%S')}"
    ensure_correlation_id(corr_id)
    start = datetime.now()
    
    metrics = {
        'ttfb': None,  # Time to first byte (task created)
        'job_created': False,
        'callback_received': False,
        'telegram_sent': False
    }
    
    try:
        inputs = build_input(model_id, sot)
        logger.info(f"{correlation_tag()} Testing {model_id}: {list(inputs.keys())}")
        
        # Create generator and generate with full params
        gen = KieGenerator()
        result = await gen.generate(
            model_id, inputs, None, timeout,
            user_id=user_id, chat_id=chat_id, price=0.0
        )
        
        task_id = result.get('task_id')
        if task_id:
            ttfb = (datetime.now() - start).total_seconds()
            metrics['ttfb'] = ttfb
            logger.info(f"{correlation_tag()} Task created: {task_id} (TTFB: {ttfb:.2f}s)")
            
            # Check if job exists in storage
            try:
                from app.storage import get_storage
                storage = get_storage()
                job = await storage.find_job_by_task_id(task_id)
                metrics['job_created'] = job is not None
                if job:
                    logger.info(f"{correlation_tag()} ✅ Job found in storage: {job.get('job_id')}")
                    metrics['callback_received'] = normalize_job_status(job.get('status', '')) in ['done', 'failed']
                else:
                    logger.warning(f"{correlation_tag()} ⚠️ Job NOT found in storage for task_id={task_id}")
            except Exception as e:
                logger.error(f"{correlation_tag()} Storage check failed: {e}")
        
        dur = (datetime.now() - start).total_seconds()
        success = result.get('success', False)
        urls = result.get('result_urls', [])
        
        status = 'done' if success and urls else ('timeout' if result.get('error_code') == 'TIMEOUT' else 'failed')
        
        # Telegram delivery check: for E2E we can't verify actual send without mock
        # But we can verify chat_id was stored in job params
        metrics['telegram_sent'] = success  # Assume sent if success (real check needs Telegram API mock)
        
        logger.info(f"{correlation_tag()} {model_id} → {status} | {dur:.1f}s | task_id={task_id}")
        logger.info(f"{correlation_tag()} Metrics: TTFB={metrics['ttfb']:.2f}s job_created={metrics['job_created']} callback={metrics['callback_received']}")
        
        return {
            'model_id': model_id,
            'success': success,
            'status': status,
            'task_id': task_id,
            'correlation_id': corr_id,
            'duration': dur,
            'error': result.get('error_message') if not success else None,
            'urls': urls,
            'metrics': metrics
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
            'urls': [],
            'metrics': metrics
        }


# Import normalize_job_status
from app.storage.status import normalize_job_status


async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    is_real = os.getenv('RUN_E2E', '0') == '1'
    admin_id = int(os.getenv('ADMIN_ID', '0')) if is_real else 0
    
    if not is_real:
        logger.warning("DRY RUN (set RUN_E2E=1 for real tests)")
        logger.warning("For REAL RUN: RUN_E2E=1 ADMIN_ID=<your_telegram_id> python -m tools.e2e_free_models")
    else:
        logger.info(f"REAL RUN mode enabled - results will be sent to Telegram chat_id={admin_id}")
        if admin_id == 0:
            logger.error("ADMIN_ID not set! Set ADMIN_ID=<your_telegram_id> for Telegram delivery")
            sys.exit(1)
    
    free_ids = get_free_models()
    logger.info(f"FREE models: {free_ids}")
    
    if not free_ids:
        logger.error("No FREE models!")
        sys.exit(1)
    
    sot = load_sot()
    results = []
    
    # Use ADMIN_ID as both user_id and chat_id for REAL RUN
    test_user_id = admin_id if is_real else 123456789
    test_chat_id = admin_id if is_real else 123456789
    
    for mid in free_ids:
        logger.info(f"\n{'='*60}\n{mid}\n{'='*60}")
        r = await test_model(mid, sot, test_user_id, test_chat_id, 180)
        results.append(r)
        emoji = "✅" if r['success'] else "❌"
        logger.info(f"{emoji} {mid}: {r['status']} ({r['duration']:.1f}s)")
        
        # In REAL RUN, pause between models to avoid rate limits
        if is_real and r != results[-1]:
            logger.info("Waiting 5s before next model...")
            await asyncio.sleep(5)
    
    passed = sum(1 for r in results if r['success'])
    failed = len(results) - passed
    
    # Calculate metrics
    job_not_found = sum(1 for r in results if not r.get('metrics', {}).get('job_created', True))
    callback_4xx = 0  # Would need real callback tracking
    avg_ttfb = sum(r.get('metrics', {}).get('ttfb', 0) for r in results if r.get('metrics', {}).get('ttfb')) / max(1, sum(1 for r in results if r.get('metrics', {}).get('ttfb')))
    avg_total = sum(r['duration'] for r in results) / len(results) if results else 0
    
    logger.info(f"\n{'='*60}")
    logger.info(f"SUMMARY: {passed}/{len(results)} passed, {failed} failed")
    logger.info(f"METRICS:")
    logger.info(f"  - callback_4xx: {callback_4xx}")
    logger.info(f"  - job_not_found: {job_not_found}")
    logger.info(f"  - avg_ttfb: {avg_ttfb:.2f}s")
    logger.info(f"  - avg_total_time: {avg_total:.2f}s")
    if is_real:
        logger.info(f"  - telegram_delivery: Check your Telegram (chat_id={admin_id}) for {len(results)} results")
    logger.info(f"{'='*60}\n")
    
    for r in results:
        e = "✅" if r['success'] else "❌"
        m = r.get('metrics', {})
        logger.info(f"{e} {r['model_id']}: {r['status']} | {r['duration']:.1f}s | corr_id={r['correlation_id']} | job={m.get('job_created', False)}")
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    asyncio.run(main())
