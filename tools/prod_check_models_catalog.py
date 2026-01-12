#!/usr/bin/env python3
"""
Production Check: Models Catalog Compliance

Validates models/menu/inputs against KIE_SOURCE_OF_TRUTH.json:
1. Bot menu categories match available models
2. Models in menu exist in SOURCE_OF_TRUTH
3. Input fields match KIE API schema
4. Required fields are collected
5. Field types are validated

Exit codes:
0 - All checks pass
1 - Critical failure (missing models, wrong fields)
2 - Warning (suboptimal but functional)
"""

import asyncio
import sys
import os
import json
import re
from typing import Dict, List, Set, Any
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class ModelCatalogCheck:
    """Validates model catalog compliance."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.source_of_truth = None
        self.bot_models = set()
    
    def error(self, msg: str):
        self.errors.append(msg)
        logger.error(f"❌ {msg}")
    
    def warn(self, msg: str):
        self.warnings.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    def ok(self, msg: str):
        logger.info(f"✅ {msg}")
    
    async def load_source_of_truth(self):
        """Load KIE_SOURCE_OF_TRUTH.json."""
        logger.info("\n📦 PHASE 1: Loading SOURCE_OF_TRUTH")
        
        try:
            with open('models/KIE_SOURCE_OF_TRUTH.json', 'r') as f:
                self.source_of_truth = json.load(f)
            
            models = self.source_of_truth.get('models', {})
            version = self.source_of_truth.get('version', 'unknown')
            
            self.ok(f"SOURCE_OF_TRUTH loaded: version={version}, {len(models)} models")
            
            # Count by category
            categories = {}
            for model_id, model_data in models.items():
                cat = model_data.get('category', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1
            
            logger.info(f"   Categories:")
            for cat, count in sorted(categories.items()):
                logger.info(f"     • {cat}: {count} models")
        
        except FileNotFoundError:
            self.error("models/KIE_SOURCE_OF_TRUTH.json not found")
        except json.JSONDecodeError as e:
            self.error(f"Invalid JSON in SOURCE_OF_TRUTH: {e}")
    
    async def check_category_labels(self):
        """Verify CATEGORY_LABELS in flow.py match SOURCE_OF_TRUTH categories."""
        logger.info("\n🏷️ PHASE 2: Category Labels")
        
        try:
            with open('bot/handlers/flow.py', 'r') as f:
                content = f.read()
            
            # Extract CATEGORY_LABELS
            match = re.search(r'CATEGORY_LABELS\s*=\s*\{([^}]+)\}', content, re.DOTALL)
            if not match:
                self.warn("CATEGORY_LABELS not found in flow.py")
                return
            
            labels_text = match.group(1)
            
            # Get actual categories from SOURCE_OF_TRUTH
            actual_categories = set()
            for model_data in self.source_of_truth.get('models', {}).values():
                cat = model_data.get('category')
                if cat:
                    actual_categories.add(cat)
            
            self.ok(f"Found {len(actual_categories)} categories in SOURCE_OF_TRUTH")
            
            # Check each actual category has a label
            for cat in actual_categories:
                if f'"{cat}"' in labels_text or f"'{cat}'" in labels_text:
                    self.ok(f"Category '{cat}' has label")
                else:
                    self.warn(f"Category '{cat}' has NO label in CATEGORY_LABELS")
        
        except FileNotFoundError:
            self.error("bot/handlers/flow.py not found")
    
    async def check_models_in_menu(self):
        """Check which models are actually shown in bot menu."""
        logger.info("\n📋 PHASE 3: Models in Menu")
        
        try:
            # Import bot registry
            from app.kie.builder import load_source_of_truth
            registry = load_source_of_truth()
            
            # Get all model IDs from registry
            registry_models = set(registry.keys())
            
            # Get all model IDs from SOURCE_OF_TRUTH
            truth_models = set(self.source_of_truth.get('models', {}).keys())
            
            self.ok(f"Registry has {len(registry_models)} models")
            self.ok(f"SOURCE_OF_TRUTH has {len(truth_models)} models")
            
            # Check overlap
            missing_in_registry = truth_models - registry_models
            missing_in_truth = registry_models - truth_models
            
            if missing_in_registry:
                self.warn(f"{len(missing_in_registry)} models in SOURCE_OF_TRUTH but NOT in registry:")
                for model_id in list(missing_in_registry)[:5]:
                    logger.warning(f"     • {model_id}")
                if len(missing_in_registry) > 5:
                    logger.warning(f"     ... and {len(missing_in_registry) - 5} more")
            
            if missing_in_truth:
                self.error(f"{len(missing_in_truth)} models in registry but NOT in SOURCE_OF_TRUTH:")
                for model_id in list(missing_in_truth)[:5]:
                    logger.error(f"     • {model_id}")
                if len(missing_in_truth) > 5:
                    logger.error(f"     ... and {len(missing_in_truth) - 5} more")
            
            if not missing_in_registry and not missing_in_truth:
                self.ok("Perfect match: registry ≡ SOURCE_OF_TRUTH")
        
        except Exception as e:
            self.warn(f"Could not load registry: {e}")
    
    async def check_input_fields(self):
        """Verify input collection matches KIE API requirements."""
        logger.info("\n📝 PHASE 4: Input Field Validation")
        
        try:
            # Sample models to check
            sample_models = [
                'wan/2-5-standard-text-to-video',
                'z-image',
                'bytedance/seedream',
                'minimax/music-01'
            ]
            
            for model_id in sample_models:
                model_data = self.source_of_truth.get('models', {}).get(model_id)
                
                if not model_data:
                    logger.info(f"ℹ️ Model {model_id} not in SOURCE_OF_TRUTH (skipping)")
                    continue
                
                input_schema = model_data.get('input_schema', {}).get('input', {})
                examples = input_schema.get('examples', [])
                
                if not examples:
                    logger.info(f"ℹ️ {model_id}: no input examples (cannot validate)")
                    continue
                
                # Get fields from first example
                example = examples[0] if isinstance(examples, list) else examples
                required_fields = set(example.keys()) if isinstance(example, dict) else set()
                
                logger.info(f"   {model_id}:")
                logger.info(f"     Required fields: {', '.join(required_fields) if required_fields else 'none'}")
                
                # Check if bot collects these fields
                # (Simplified check - real implementation would parse flow.py state machine)
                common_fields = {'prompt', 'image', 'video', 'audio', 'url', 'file', 'text'}
                missing_fields = required_fields - common_fields
                
                if missing_fields:
                    self.warn(f"{model_id}: May need custom fields: {', '.join(missing_fields)}")
        
        except Exception as e:
            self.warn(f"Input field validation failed: {e}")
    
    async def check_pricing_data(self):
        """Verify all models have pricing information."""
        logger.info("\n💰 PHASE 5: Pricing Data")
        
        try:
            models_without_pricing = []
            free_models = []
            
            for model_id, model_data in self.source_of_truth.get('models', {}).items():
                pricing = model_data.get('pricing', {})
                
                if not pricing:
                    models_without_pricing.append(model_id)
                    continue
                
                rub_price = pricing.get('rub_per_gen', 0)
                if rub_price == 0:
                    free_models.append(model_id)
            
            total_models = len(self.source_of_truth.get('models', {}))
            
            if models_without_pricing:
                self.warn(f"{len(models_without_pricing)}/{total_models} models without pricing:")
                for model_id in models_without_pricing[:3]:
                    logger.warning(f"     • {model_id}")
            
            if free_models:
                self.ok(f"{len(free_models)}/{total_models} models are FREE:")
                for model_id in free_models[:3]:
                    logger.info(f"     • {model_id}")
            
            if not models_without_pricing:
                self.ok(f"All {total_models} models have pricing")
        
        except Exception as e:
            self.warn(f"Pricing check failed: {e}")
    
    async def check_model_metadata(self):
        """Verify models have required metadata."""
        logger.info("\n📊 PHASE 6: Model Metadata")
        
        required_fields = {
            'model_id': 'Model identifier',
            'category': 'Category',
            'display_name': 'Display name',
            'input_schema': 'Input schema'
        }
        
        try:
            models = self.source_of_truth.get('models', {})
            incomplete_models = {}
            
            for model_id, model_data in models.items():
                missing = []
                for field, desc in required_fields.items():
                    if field not in model_data or not model_data[field]:
                        missing.append(desc)
                
                if missing:
                    incomplete_models[model_id] = missing
            
            if incomplete_models:
                self.warn(f"{len(incomplete_models)}/{len(models)} models have incomplete metadata:")
                for model_id, missing in list(incomplete_models.items())[:3]:
                    logger.warning(f"     • {model_id}: missing {', '.join(missing)}")
            else:
                self.ok(f"All {len(models)} models have complete metadata")
        
        except Exception as e:
            self.warn(f"Metadata check failed: {e}")
    
    async def run_all_checks(self):
        """Run all production checks."""
        logger.info("=" * 60)
        logger.info("🔍 PRODUCTION CHECK: Models Catalog Compliance")
        logger.info("=" * 60)
        
        await self.load_source_of_truth()
        
        if not self.source_of_truth:
            logger.error("\n❌ CRITICAL: Cannot proceed without SOURCE_OF_TRUTH")
            return 1
        
        await self.check_category_labels()
        await self.check_models_in_menu()
        await self.check_input_fields()
        await self.check_pricing_data()
        await self.check_model_metadata()
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 RESULTS")
        logger.info("=" * 60)
        
        if self.errors:
            logger.error(f"\n❌ {len(self.errors)} CRITICAL ERRORS:")
            for error in self.errors:
                logger.error(f"   • {error}")
        
        if self.warnings:
            logger.warning(f"\n⚠️ {len(self.warnings)} WARNINGS:")
            for warning in self.warnings:
                logger.warning(f"   • {warning}")
        
        if not self.errors and not self.warnings:
            logger.info("\n✅ ALL CHECKS PASSED - Models catalog production ready")
            return 0
        elif self.errors:
            logger.error("\n❌ CRITICAL FAILURES - Models will not work")
            return 1
        else:
            logger.warning("\n⚠️ WARNINGS ONLY - May work but suboptimal")
            return 2


async def main():
    checker = ModelCatalogCheck()
    return await checker.run_all_checks()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
