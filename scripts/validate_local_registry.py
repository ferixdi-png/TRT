#!/usr/bin/env python3
"""
Local Registry Validator - Fail-fast validation at startup (DRY_RUN mode).

Validates:
1. All models have required fields
2. No missing required fields in input_schema
3. Defaults are valid (enums include default, constraints satisfied)
4. No duplicate model_ids
5. Categories are valid
6. Pricing is consistent
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Set

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

VALID_CATEGORIES = {"image", "video", "audio", "enhance", "music", "avatar", "other"}


class LocalRegistryValidator:
    """Validates local KIE_SOURCE_OF_TRUTH.json for internal consistency."""
    
    def __init__(self, sot_path: str = "models/KIE_SOURCE_OF_TRUTH.json"):
        self.sot_path = Path(sot_path)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.models: Dict[str, Any] = {}
    
    def load_registry(self) -> bool:
        """Load registry from file."""
        if not self.sot_path.exists():
            self.errors.append(f"Registry file not found: {self.sot_path}")
            return False
        
        try:
            with open(self.sot_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.models = data.get("models", {})
            return True
        except Exception as e:
            self.errors.append(f"Failed to load registry: {e}")
            return False
    
    def validate_required_fields(self):
        """Validate all models have required top-level fields."""
        required = {"model_id", "category", "endpoint", "input_schema"}
        
        for model_id, model_data in self.models.items():
            missing = required - set(model_data.keys())
            if missing:
                self.errors.append(f"{model_id}: Missing required fields: {missing}")
    
    def validate_categories(self):
        """Validate categories are in allowed set."""
        for model_id, model_data in self.models.items():
            category = model_data.get("category")
            if category and category not in VALID_CATEGORIES:
                self.warnings.append(f"{model_id}: Unknown category '{category}'")
    
    def validate_input_schema(self):
        """Validate input_schema structure and consistency."""
        for model_id, model_data in self.models.items():
            input_schema = model_data.get("input_schema", {})
            if not input_schema:
                self.errors.append(f"{model_id}: Missing input_schema")
                continue
            
            input_props = input_schema.get("input", {})
            if not input_props:
                self.errors.append(f"{model_id}: Missing input_schema.input")
                continue
            
            # Check if it has "properties" or "examples"
            if "properties" in input_props:
                self._validate_properties(model_id, input_props["properties"], input_props.get("required", []))
            elif "examples" in input_props:
                # Examples format - can't validate as strictly
                self.warnings.append(f"{model_id}: Using examples format (properties preferred)")
    
    def _validate_properties(self, model_id: str, properties: Dict[str, Any], required: List[str]):
        """Validate properties structure."""
        for field_name, field_spec in properties.items():
            # Check default is in enum if enum exists
            if "enum" in field_spec or "options" in field_spec:
                enum_values = field_spec.get("enum") or field_spec.get("options", [])
                default = field_spec.get("default")
                if default is not None and default not in enum_values:
                    self.errors.append(
                        f"{model_id}.{field_name}: Default '{default}' not in enum {enum_values}"
                    )
            
            # Check constraints are valid
            if "max_length" in field_spec:
                max_len = field_spec["max_length"]
                if not isinstance(max_len, int) or max_len <= 0:
                    self.errors.append(f"{model_id}.{field_name}: Invalid max_length: {max_len}")
            
            # Check required fields are in properties
            if field_name in required and not field_spec.get("required", False):
                self.warnings.append(
                    f"{model_id}.{field_name}: In required list but field_spec.required=False"
                )
    
    def validate_no_duplicates(self):
        """Check for duplicate model_ids."""
        seen_ids: Set[str] = set()
        for model_id, model_data in self.models.items():
            # Check model_id field matches key
            model_id_field = model_data.get("model_id")
            if model_id_field and model_id_field != model_id:
                self.warnings.append(
                    f"{model_id}: model_id field '{model_id_field}' doesn't match key"
                )
            
            if model_id in seen_ids:
                self.errors.append(f"Duplicate model_id: {model_id}")
            seen_ids.add(model_id)
    
    def validate_pricing(self):
        """Validate pricing structure."""
        for model_id, model_data in self.models.items():
            pricing = model_data.get("pricing", {})
            if not pricing:
                self.warnings.append(f"{model_id}: No pricing information")
                continue
            
            # Check pricing_rules if present
            pricing_rules = pricing.get("pricing_rules")
            if pricing_rules:
                strategy = pricing_rules.get("strategy")
                if strategy == "by_resolution":
                    resolution_map = pricing_rules.get("resolution", {})
                    if not resolution_map:
                        self.errors.append(f"{model_id}: pricing_rules.resolution is empty")
    
    def run(self) -> bool:
        """Run all validations."""
        print("=" * 80)
        print("LOCAL REGISTRY VALIDATOR")
        print("=" * 80)
        
        if not self.load_registry():
            return False
        
        print(f"✅ Loaded {len(self.models)} models")
        
        self.validate_required_fields()
        self.validate_categories()
        self.validate_input_schema()
        self.validate_no_duplicates()
        self.validate_pricing()
        
        # Report
        print("\n" + "=" * 80)
        print("VALIDATION RESULTS")
        print("=" * 80)
        print(f"✅ Models checked: {len(self.models)}")
        print(f"❌ Errors: {len(self.errors)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        
        if self.errors:
            print("\n❌ ERRORS:")
            for err in self.errors[:20]:
                print(f"   • {err}")
            if len(self.errors) > 20:
                print(f"   ... and {len(self.errors) - 20} more")
        
        if self.warnings:
            print("\n⚠️  WARNINGS (first 10):")
            for warn in self.warnings[:10]:
                print(f"   • {warn}")
            if len(self.warnings) > 10:
                print(f"   ... and {len(self.warnings) - 10} more")
        
        print("\n" + "=" * 80)
        
        if self.errors:
            print("❌ VALIDATION FAILED")
            return False
        else:
            print("✅ VALIDATION PASSED")
            return True


def main():
    validator = LocalRegistryValidator()
    success = validator.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

