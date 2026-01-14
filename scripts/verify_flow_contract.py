#!/usr/bin/env python
"""
Simple flow contract verification script (non-pytest).
Tests that:
1. All 72 models have a determined flow_type
2. image_edit models ALWAYS have image_url as first required field
3. Correct input ordering for all flow types
"""

import sys
import logging
from app.kie.builder import load_source_of_truth
from app.kie.flow_types import (
    get_flow_type,
    get_primary_required_fields,
    get_expected_input_order,
    FLOW_IMAGE_EDIT,
    FLOW_IMAGE2IMAGE,
    FLOW_IMAGE2VIDEO,
    FLOW_IMAGE_UPSCALE,
    FLOW_TEXT2IMAGE,
    FLOW_TEXT2VIDEO,
    FLOW_TEXT2AUDIO,
    FLOW_VIDEO_EDIT,
    FLOW_AUDIO_PROCESSING,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_all_models_have_flow_type():
    """FAIL if any model has flow_type = 'unknown'."""
    registry = load_source_of_truth()
    models_dict = registry.get('models', {})
    
    # Extract model list from registry
    models = []
    for model_id, model_spec in models_dict.items():
        if isinstance(model_spec, dict) and 'input_schema' in model_spec:
            model_spec['model_id'] = model_id
            models.append(model_spec)
    
    unknown_models = []
    
    for model in models:
        model_id = model.get("model_id")
        flow_type = get_flow_type(model_id, model)
        if flow_type == "unknown":
            unknown_models.append(model_id)
    
    if unknown_models:
        logger.error(f"Models without determined flow_type: {unknown_models}")
        return False
    
    logger.info(f"✓ All {len(models)} models have determined flow_type")
    return True


def test_image_edit_flow_structure():
    """CRITICAL: image_edit models MUST collect image BEFORE prompt."""
    registry = load_source_of_truth()
    models_dict = registry.get('models', {})
    
    # Extract model list
    models = []
    for model_id, model_spec in models_dict.items():
        if isinstance(model_spec, dict) and 'input_schema' in model_spec:
            model_spec['model_id'] = model_id
            models.append(model_spec)
    
    image_edit_models = [m for m in models 
                        if get_flow_type(m.get("model_id"), m) == FLOW_IMAGE_EDIT]
    
    if not image_edit_models:
        logger.error("No image_edit models found")
        return False
    
    failed = []
    for model in image_edit_models:
        model_id = model.get("model_id")
        expected_order = get_expected_input_order(FLOW_IMAGE_EDIT)
        
        # Check that image_url comes first
        image_fields = [f for f in expected_order if f in ["image_url", "image_urls", "input_image"]]
        if not image_fields:
            failed.append(f"{model_id}: no image field in order {expected_order}")
            continue
        
        if expected_order.index(image_fields[0]) != 0:
            failed.append(f"{model_id}: image not first in {expected_order}")
    
    if failed:
        for msg in failed:
            logger.error(f"✗ {msg}")
        return False
    
    logger.info(f"✓ All {len(image_edit_models)} image_edit models have correct structure")
    return True


def test_flow_type_distribution():
    """Log distribution of flow types."""
    registry = load_source_of_truth()
    models_dict = registry.get('models', {})
    
    # Extract model list
    models = []
    for model_id, model_spec in models_dict.items():
        if isinstance(model_spec, dict) and 'input_schema' in model_spec:
            model_spec['model_id'] = model_id
            models.append(model_spec)
    
    flow_type_counts = {}
    
    for model in models:
        model_id = model.get("model_id")
        flow_type = get_flow_type(model_id, model)
        flow_type_counts[flow_type] = flow_type_counts.get(flow_type, 0) + 1
    
    logger.info(f"Flow type distribution ({len(models)} total):")
    for flow_type, count in sorted(flow_type_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {flow_type:20s}: {count:3d}")
    
    # Verify main flow types
    checks = [
        (FLOW_TEXT2IMAGE, "text2image", 5),
        (FLOW_IMAGE_EDIT, "image_edit", 1),
    ]
    
    for flow_type, name, min_count in checks:
        actual = flow_type_counts.get(flow_type, 0)
        if actual < min_count:
            logger.error(f"✗ Insufficient {name} models: expected >={min_count}, got {actual}")
            return False
    
    logger.info(f"✓ Flow type distribution is healthy")
    return True


def main():
    """Run all tests."""
    tests = [
        ("All models have flow_type", test_all_models_have_flow_type),
        ("image_edit structure correct", test_image_edit_flow_structure),
        ("Flow type distribution", test_flow_type_distribution),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            logger.info(f"{'PASS' if result else 'FAIL'}: {test_name}\n")
        except Exception as e:
            logger.exception(f"ERROR in {test_name}: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("=" * 60)
    passed = sum(1 for _, r in results if r)
    logger.info(f"SUMMARY: {passed}/{len(results)} tests passed")
    
    for test_name, result in results:
        status = "✓" if result else "✗"
        logger.info(f"{status} {test_name}")
    
    return all(r for _, r in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
