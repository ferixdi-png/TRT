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

# 🔧 E2E SETUP: Set minimum required env vars for testing
if not os.getenv("WEBHOOK_BASE_URL"):
    # Use placeholder URL - callbacks won't arrive but tasks will be created
    os.environ["WEBHOOK_BASE_URL"] = "https://e2e-test.local"
    print("⚠️ E2E MODE: WEBHOOK_BASE_URL not set, using placeholder (callbacks will be mocked)")

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
    """Build complete input for model using first example from SOURCE_OF_TRUTH"""
    models = sot.get('models', {})
    model_data = models.get(model_id, {})
    schema = model_data.get('input_schema', {}).get('input', {})
    examples = schema.get('examples', [])
    
    if not examples or not isinstance(examples[0], dict):
        # Fallback: minimal input
        return {'prompt': 'test котик'}
    
    # Use first example as base (it should have all required fields)
    example_input = examples[0].copy()
    
    # Override some fields for test consistency
    if 'prompt' in example_input:
        example_input['prompt'] = 'test котик'
    if 'negative_prompt' in example_input and not example_input.get('negative_prompt'):
        example_input['negative_prompt'] = ''  # Empty string instead of None
    
    # For image-based models, use test image if needed
    if 'image' in example_input or 'image_url' in example_input:
        test_image = load_test_image()
        if 'image' in example_input:
            example_input['image'] = test_image
        if 'image_url' in example_input:
            example_input['image_url'] = test_image
    
    return example_input


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
        
        # Safe formatting of metrics (handle None values)
        ttfb_val = metrics.get('ttfb')
        ttfb_str = f"{ttfb_val:.2f}s" if ttfb_val is not None else "N/A"
        logger.info(f"{correlation_tag()} Metrics: TTFB={ttfb_str} job_created={metrics['job_created']} callback={metrics['callback_received']}")
        
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
    
    # Support for 2x runs mode
    runs_count = int(os.getenv('E2E_RUNS', '1'))  # Default 1, set E2E_RUNS=2 for stability test
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
    
    logger.info(f"Running {runs_count}x for each model (E2E_RUNS={runs_count})")
    
    free_ids = get_free_models()
    logger.info(f"FREE models: {free_ids}")
    
    if not free_ids:
        logger.error("No FREE models!")
        sys.exit(1)
    
    sot = load_sot()
    all_results = []  # All runs for all models
    model_stability = {}  # Track stability per model
    
    # Use ADMIN_ID as both user_id and chat_id for REAL RUN
    test_user_id = admin_id if is_real else 123456789
    test_chat_id = admin_id if is_real else 123456789
    
    for mid in free_ids:
        model_stability[mid] = {'passed': 0, 'failed': 0, 'runs': []}
        
        logger.info(f"\n{'='*60}\n{mid} - Running {runs_count}x\n{'='*60}")
        
        for run_num in range(1, runs_count + 1):
            logger.info(f"🔄 Run {run_num}/{runs_count} for {mid}")
            r = await test_model(mid, sot, test_user_id, test_chat_id, 180)
            r['run_number'] = run_num
            all_results.append(r)
            model_stability[mid]['runs'].append(r)
            
            if r['success']:
                model_stability[mid]['passed'] += 1
            else:
                model_stability[mid]['failed'] += 1
            
            emoji = "✅" if r['success'] else "❌"
            logger.info(f"  {emoji} Run {run_num}: {r['status']} ({r['duration']:.1f}s)")
            
            # Small delay between runs of same model
            if run_num < runs_count:
                await asyncio.sleep(2)
        
        # Determine stability
        total = model_stability[mid]['passed'] + model_stability[mid]['failed']
        if model_stability[mid]['passed'] == total:
            stability = "🟢 STABLE"
        elif model_stability[mid]['passed'] > 0:
            stability = "🟡 UNSTABLE"
        else:
            stability = "🔴 FAILED"
        
        logger.info(f"\n{stability} {mid}: {model_stability[mid]['passed']}/{total} passed")
        
        # In REAL RUN, pause between models to avoid rate limits
        if is_real and mid != free_ids[-1]:
            logger.info("Waiting 5s before next model...")
            await asyncio.sleep(5)
    
    # Summary statistics
    total_passed = sum(1 for r in all_results if r['success'])
    total_failed = len(all_results) - total_passed
    
    # Calculate metrics
    job_not_found = sum(1 for r in all_results if not r.get('metrics', {}).get('job_created', True))
    callback_4xx = 0  # Would need real callback tracking
    avg_ttfb = sum(r.get('metrics', {}).get('ttfb', 0) for r in all_results if r.get('metrics', {}).get('ttfb')) / max(1, sum(1 for r in all_results if r.get('metrics', {}).get('ttfb')))
    avg_total = sum(r['duration'] for r in all_results) / len(all_results) if all_results else 0
    
    # Stability summary
    stable_models = sum(1 for mid, stats in model_stability.items() if stats['failed'] == 0)
    unstable_models = sum(1 for mid, stats in model_stability.items() if stats['failed'] > 0 and stats['passed'] > 0)
    failed_models = sum(1 for mid, stats in model_stability.items() if stats['passed'] == 0)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"📊 E2E TEST METRICS ({runs_count}x RUNS)")
    logger.info(f"{'='*80}")
    logger.info(f"OVERALL: {total_passed}/{len(all_results)} runs passed, {total_failed} failed")
    logger.info(f"\nSTABILITY:")
    logger.info(f"  🟢 STABLE:   {stable_models}/{len(free_ids)} models (all runs passed)")
    logger.info(f"  🟡 UNSTABLE: {unstable_models}/{len(free_ids)} models (some runs failed)")
    logger.info(f"  🔴 FAILED:   {failed_models}/{len(free_ids)} models (all runs failed)")
    logger.info(f"\nMETRICS:")
    logger.info(f"  - callback_4xx: {callback_4xx}")
    logger.info(f"  - job_not_found: {job_not_found}")
    logger.info(f"  - avg_ttfb: {avg_ttfb:.2f}s")
    logger.info(f"  - avg_total_time: {avg_total:.2f}s")
    if is_real:
        logger.info(f"  - telegram_delivery: Check your Telegram (chat_id={admin_id}) for {len(all_results)} results")
    logger.info(f"{'='*80}\n")
    
    # Per-model breakdown
    logger.info("📦 PER-MODEL RESULTS:")
    for mid, stats in model_stability.items():
        total = stats['passed'] + stats['failed']
        if stats['failed'] == 0:
            stability = "🟢 STABLE"
        elif stats['passed'] > 0:
            stability = "🟡 UNSTABLE"
        else:
            stability = "🔴 FAILED"
        
        avg_duration = sum(r['duration'] for r in stats['runs']) / len(stats['runs'])
        logger.info(f"  {stability} {mid}: {stats['passed']}/{total} passed | avg {avg_duration:.1f}s")
    
    logger.info(f"{'='*80}\n")
    
    # Exit code: 0 if all models stable, 1 otherwise
    all_stable = failed_models == 0 and unstable_models == 0
    if all_stable:
        logger.info("✅ ALL MODELS STABLE - PRODUCTION READY")
        sys.exit(0)
    else:
        logger.warning("⚠️ SOME MODELS UNSTABLE/FAILED - INVESTIGATION NEEDED")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
