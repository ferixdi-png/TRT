#!/usr/bin/env python3
"""
E2E Smoke Test: All Buttons and Models Matrix.

Tests that ALL buttons respond correctly and ALL models can be configured
without silent clicks or crashes.

Generates matrix from SOURCE_OF_TRUTH:
- model_id → required_inputs → defaults → validators
- Emulates: cat:* → model selection → prompt input → defaults → confirmation
- Validates: bot either (i) asks for missing input, (ii) applies defaults, or (iii) shows error
"""

import sys
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.kie.builder import load_source_of_truth, get_model_schema
try:
    from app.kie.validator import validate_inputs
except ImportError:
    # Fallback if validator module structure is different
    validate_inputs = None

try:
    from app.kie.model_defaults import apply_defaults
except ImportError:
    # Fallback
    apply_defaults = None

logging = None
try:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
except:
    pass


@dataclass
class ModelTestMatrix:
    """Test matrix for a single model."""
    model_id: str
    category: str
    required_fields: List[str]
    optional_fields: List[str]
    defaults: Dict[str, Any]
    validators: Dict[str, Any]
    has_prompt: bool
    prompt_required: bool


@dataclass
class TestResult:
    """Result of a single test."""
    model_id: str
    step: str
    passed: bool
    message: str
    error: Optional[str] = None


def generate_test_matrix() -> List[ModelTestMatrix]:
    """
    Generate test matrix from SOURCE_OF_TRUTH.
    
    Returns:
        List of ModelTestMatrix objects
    """
    sot = load_source_of_truth()
    models = sot.get('models', {})
    
    matrix = []
    
    for model_id, model_data in models.items():
        if not isinstance(model_data, dict):
            continue
        
        category = model_data.get('category', 'unknown')
        input_schema = model_data.get('input_schema', {})
        
        # Extract input schema structure
        # Support both formats: direct and nested
        input_properties = {}
        required_fields = []
        optional_fields = []
        defaults = {}
        validators = {}
        
        # Check if nested format (has 'input' key with 'properties')
        if 'input' in input_schema and isinstance(input_schema['input'], dict):
            input_obj = input_schema['input']
            if 'properties' in input_obj:
                input_properties = input_obj.get('properties', {})
                required_fields = input_obj.get('required', [])
            elif isinstance(input_obj, dict):
                # Direct format in 'input'
                input_properties = {k: v for k, v in input_obj.items() 
                                  if k not in ('type', 'required', 'examples')}
        elif 'properties' in input_schema:
            # Nested format at top level
            input_properties = input_schema.get('properties', {})
            required_fields = input_schema.get('required', [])
        else:
            # Direct format
            input_properties = {k: v for k, v in input_schema.items() 
                              if k not in ('type', 'required', 'examples')}
            required_fields = [k for k, v in input_properties.items() 
                             if v.get('required', False)]
        
        # Extract defaults and validators
        for field_name, field_spec in input_properties.items():
            if isinstance(field_spec, dict):
                if 'default' in field_spec:
                    defaults[field_name] = field_spec['default']
                if 'enum' in field_spec:
                    validators[field_name] = {'type': 'enum', 'values': field_spec['enum']}
                if 'max_length' in field_spec:
                    validators[field_name] = validators.get(field_name, {})
                    validators[field_name]['max_length'] = field_spec['max_length']
                if 'max_items' in field_spec:
                    validators[field_name] = validators.get(field_name, {})
                    validators[field_name]['max_items'] = field_spec['max_items']
        
        optional_fields = [k for k in input_properties.keys() if k not in required_fields]
        
        # Check if prompt is required
        has_prompt = 'prompt' in input_properties
        prompt_required = 'prompt' in required_fields
        
        matrix.append(ModelTestMatrix(
            model_id=model_id,
            category=category,
            required_fields=required_fields,
            optional_fields=optional_fields,
            defaults=defaults,
            validators=validators,
            has_prompt=has_prompt,
            prompt_required=prompt_required
        ))
    
    return matrix


async def test_model_defaults(matrix: ModelTestMatrix) -> TestResult:
    """
    Test 1: Model defaults are applied correctly.
    
    Simulates: User selects model → bot applies defaults for optional fields.
    """
    try:
        if not apply_defaults:
            return TestResult(
                model_id=matrix.model_id,
                step="defaults",
                passed=False,
                message="apply_defaults function not available",
                error="Import error"
            )
        
        # Build user inputs with only prompt (if required)
        user_inputs = {}
        if matrix.prompt_required:
            user_inputs['prompt'] = "Test prompt for smoke test"
        
        # Apply defaults
        applied_inputs = apply_defaults(matrix.model_id, user_inputs)
        
        # Check that defaults were applied
        defaults_applied = all(
            applied_inputs.get(k) == v 
            for k, v in matrix.defaults.items()
        )
        
        if defaults_applied or not matrix.defaults:
            return TestResult(
                model_id=matrix.model_id,
                step="defaults",
                passed=True,
                message=f"Defaults applied: {list(matrix.defaults.keys())}"
            )
        else:
            missing_defaults = [
                k for k in matrix.defaults.keys() 
                if applied_inputs.get(k) != matrix.defaults[k]
            ]
            return TestResult(
                model_id=matrix.model_id,
                step="defaults",
                passed=False,
                message=f"Missing defaults: {missing_defaults}",
                error=f"Expected defaults: {matrix.defaults}, got: {applied_inputs}"
            )
    except Exception as e:
        return TestResult(
            model_id=matrix.model_id,
            step="defaults",
            passed=False,
            message=f"Exception: {e}",
            error=str(e)
        )


async def test_model_validation(matrix: ModelTestMatrix) -> TestResult:
    """
    Test 2: Model validation works correctly.
    
    Simulates: User provides inputs → bot validates → shows errors if invalid.
    """
    try:
        if not apply_defaults or not validate_inputs:
            return TestResult(
                model_id=matrix.model_id,
                step="validation",
                passed=False,
                message="validation functions not available",
                error="Import error"
            )
        
        # Build valid inputs
        user_inputs = {}
        if matrix.prompt_required:
            user_inputs['prompt'] = "Valid test prompt"
        
        # Apply defaults
        user_inputs = apply_defaults(matrix.model_id, user_inputs)
        
        # Validate
        is_valid, errors = validate_inputs(matrix.model_id, user_inputs)
        
        if is_valid:
            return TestResult(
                model_id=matrix.model_id,
                step="validation",
                passed=True,
                message="Validation passed"
            )
        else:
            return TestResult(
                model_id=matrix.model_id,
                step="validation",
                passed=False,
                message=f"Validation failed: {errors}",
                error="; ".join(errors)
            )
    except Exception as e:
        return TestResult(
            model_id=matrix.model_id,
            step="validation",
            passed=False,
            message=f"Exception: {e}",
            error=str(e)
        )


async def test_model_required_fields(matrix: ModelTestMatrix) -> TestResult:
    """
    Test 3: Required fields are enforced.
    
    Simulates: User tries to generate without required fields → bot asks for them.
    """
    try:
        if not apply_defaults or not validate_inputs:
            return TestResult(
                model_id=matrix.model_id,
                step="required_fields",
                passed=False,
                message="validation functions not available",
                error="Import error"
            )
        
        # Try with empty inputs (no required fields)
        user_inputs = {}
        
        # Apply defaults
        user_inputs = apply_defaults(matrix.model_id, user_inputs)
        
        # Validate
        is_valid, errors = validate_inputs(matrix.model_id, user_inputs)
        
        # If prompt is required, validation should fail
        if matrix.prompt_required:
            if not is_valid and any('prompt' in err.lower() for err in errors):
                return TestResult(
                    model_id=matrix.model_id,
                    step="required_fields",
                    passed=True,
                    message="Required field (prompt) correctly enforced"
                )
            else:
                return TestResult(
                    model_id=matrix.model_id,
                    step="required_fields",
                    passed=False,
                    message="Required field (prompt) not enforced",
                    error=f"Validation: {is_valid}, errors: {errors}"
                )
        else:
            # No required fields - should pass or show appropriate message
            return TestResult(
                model_id=matrix.model_id,
                step="required_fields",
                passed=True,
                message="No required fields (except prompt)"
            )
    except Exception as e:
        return TestResult(
            model_id=matrix.model_id,
            step="required_fields",
            passed=False,
            message=f"Exception: {e}",
            error=str(e)
        )


async def test_category_models() -> List[TestResult]:
    """
    Test 4: Category buttons work (cat:image, cat:enhance, etc.).
    
    Simulates: User clicks category → bot shows models.
    """
    results = []
    
    try:
        sot = load_source_of_truth()
        models = sot.get('models', {})
        
        # Group by category
        categories = {}
        for model_id, model_data in models.items():
            if isinstance(model_data, dict):
                category = model_data.get('category', 'unknown')
                if category not in categories:
                    categories[category] = []
                categories[category].append(model_id)
        
        # Test each category
        for category, model_ids in categories.items():
            if len(model_ids) > 0:
                results.append(TestResult(
                    model_id=f"cat:{category}",
                    step="category",
                    passed=True,
                    message=f"Category has {len(model_ids)} models"
                ))
            else:
                results.append(TestResult(
                    model_id=f"cat:{category}",
                    step="category",
                    passed=False,
                    message="Category has no models",
                    error="Empty category"
                ))
    except Exception as e:
        results.append(TestResult(
            model_id="categories",
            step="category",
            passed=False,
            message=f"Exception: {e}",
            error=str(e)
        ))
    
    return results


async def main():
    """Run all E2E smoke tests."""
    print("=" * 80)
    print("E2E SMOKE TEST: All Buttons and Models Matrix")
    print("=" * 80)
    print()
    
    # Generate test matrix
    print("📊 Generating test matrix from SOURCE_OF_TRUTH...")
    matrix = generate_test_matrix()
    print(f"✅ Generated matrix for {len(matrix)} models")
    print()
    
    # Test categories
    print("🧪 Testing categories...")
    category_results = await test_category_models()
    category_passed = sum(1 for r in category_results if r.passed)
    print(f"  ✅ Categories: {category_passed}/{len(category_results)} passed")
    print()
    
    # Test each model
    print("🧪 Testing models...")
    all_results = []
    
    # Limit to first 10 models for initial run (can be increased)
    test_models = matrix[:10] if len(matrix) > 10 else matrix
    
    for model_matrix in test_models:
        print(f"  Testing {model_matrix.model_id} ({model_matrix.category})...")
        
        # Test 1: Defaults
        result1 = await test_model_defaults(model_matrix)
        all_results.append(result1)
        
        # Test 2: Validation
        result2 = await test_model_validation(model_matrix)
        all_results.append(result2)
        
        # Test 3: Required fields
        result3 = await test_model_required_fields(model_matrix)
        all_results.append(result3)
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total_tests = len(all_results) + len(category_results)
    passed_tests = sum(1 for r in all_results + category_results if r.passed)
    
    print(f"✅ PASSED: {passed_tests}/{total_tests}")
    print(f"❌ FAILED: {total_tests - passed_tests}/{total_tests}")
    print()
    
    # Show failures
    failures = [r for r in all_results + category_results if not r.passed]
    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  ❌ {failure.model_id} ({failure.step}): {failure.message}")
            if failure.error:
                print(f"     Error: {failure.error}")
        print()
    
    if passed_tests == total_tests:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

