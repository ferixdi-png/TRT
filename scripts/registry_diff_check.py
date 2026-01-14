#!/usr/bin/env python3
"""
Registry Diff Check - compares incoming vendor docs with current SOURCE_OF_TRUTH.

Usage:
    python scripts/registry_diff_check.py [vendor_doc_path]

If vendor_doc_path not provided, checks all files in kb/vendor_docs/*.md

Outputs diff report but does NOT mutate SOURCE_OF_TRUTH.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.kie.builder import load_source_of_truth, get_model_schema

logging = None
try:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
except:
    pass


def parse_vendor_doc(doc_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse vendor documentation markdown file.
    
    Expected format:
    - Model: <model_id>
    - Endpoints: POST /api/v1/jobs/createTask, GET /api/v1/jobs/recordInfo?taskId=...
    - Input schema: <field descriptions>
    - Pricing: <pricing info>
    """
    if not doc_path.exists():
        return None
    
    content = doc_path.read_text(encoding='utf-8')
    
    # Extract model ID
    model_match = re.search(r'Model:\s*([^\n]+)', content, re.IGNORECASE)
    if not model_match:
        return None
    
    model_id = model_match.group(1).strip()
    
    # Extract input schema
    schema_section = re.search(r'Input schema:([^\n]+(?:\n(?!Pricing:|Output|Important)[^\n]+)*)', content, re.IGNORECASE | re.MULTILINE)
    input_schema = {}
    if schema_section:
        schema_text = schema_section.group(1)
        # Parse field definitions
        # Format: - field_name (required/optional, type, constraints)
        field_pattern = r'-\s*(\w+)\s*\(([^)]+)\)'
        for match in re.finditer(field_pattern, schema_text):
            field_name = match.group(1)
            field_desc = match.group(2)
            
            # Parse field description
            required = 'required' in field_desc.lower()
            field_type = 'string'
            if 'array' in field_desc.lower():
                field_type = 'array'
            elif 'enum' in field_desc.lower():
                field_type = 'enum'
            
            # Extract constraints
            max_length = None
            max_items = None
            enum_values = None
            default = None
            
            # max_length
            max_len_match = re.search(r'max\s+(\d+)', field_desc, re.IGNORECASE)
            if max_len_match:
                max_length = int(max_len_match.group(1))
            
            # max_items (for arrays)
            max_items_match = re.search(r'up\s+to\s+(\d+)', field_desc, re.IGNORECASE)
            if max_items_match:
                max_items = int(max_items_match.group(1))
            
            # enum values
            enum_match = re.search(r'enum:\s*([^;]+)', field_desc, re.IGNORECASE)
            if enum_match:
                enum_text = enum_match.group(1)
                enum_values = [v.strip() for v in enum_text.split(',')]
            
            # default
            default_match = re.search(r'default\s+([^;,\n]+)', field_desc, re.IGNORECASE)
            if default_match:
                default = default_match.group(1).strip().strip('"').strip("'")
            
            input_schema[field_name] = {
                'type': field_type,
                'required': required,
                'max_length': max_length,
                'max_items': max_items,
                'enum': enum_values,
                'default': default
            }
    
    # Extract pricing
    pricing = {}
    pricing_match = re.search(r'Pricing:([^\n]+(?:\n[^\n]+)*)', content, re.IGNORECASE | re.MULTILINE)
    if pricing_match:
        pricing_text = pricing_match.group(1)
        # Try to extract credits or USD
        credits_match = re.search(r'(\d+)\s*credits?', pricing_text, re.IGNORECASE)
        if credits_match:
            pricing['credits'] = int(credits_match.group(1))
        usd_match = re.search(r'\$?(\d+\.?\d*)\s*usd', pricing_text, re.IGNORECASE)
        if usd_match:
            pricing['usd'] = float(usd_match.group(1))
    
    return {
        'model_id': model_id,
        'input_schema': input_schema,
        'pricing': pricing
    }


def compare_with_ssot(vendor_doc: Dict[str, Any], ssot: Dict[str, Any]) -> List[str]:
    """
    Compare vendor doc against SSOT and return list of differences.
    
    Returns:
        List of diff messages (empty if match)
    """
    diffs = []
    model_id = vendor_doc.get('model_id')
    
    if not model_id:
        diffs.append("❌ Vendor doc has no model_id")
        return diffs
    
    if 'models' not in ssot:
        diffs.append("❌ SSOT has no 'models' key")
        return diffs
    
    if model_id not in ssot['models']:
        diffs.append(f"❌ Model '{model_id}' not found in SSOT")
        return diffs
    
    ssot_model = ssot['models'][model_id]
    
    # Compare input schema
    vendor_schema = vendor_doc.get('input_schema', {})
    ssot_input_schema = ssot_model.get('input_schema', {})
    
    # Extract SSOT properties (support both formats)
    ssot_properties = {}
    if 'input' in ssot_input_schema and isinstance(ssot_input_schema['input'], dict):
        input_obj = ssot_input_schema['input']
        if 'properties' in input_obj:
            ssot_properties = input_obj.get('properties', {})
            ssot_required = input_obj.get('required', [])
        else:
            # Direct format in 'input'
            ssot_properties = {k: v for k, v in input_obj.items() 
                              if k not in ('type', 'required', 'examples')}
            ssot_required = [k for k, v in ssot_properties.items() 
                           if v.get('required', False)]
    elif 'properties' in ssot_input_schema:
        ssot_properties = ssot_input_schema.get('properties', {})
        ssot_required = ssot_input_schema.get('required', [])
    else:
        # Direct format
        ssot_properties = {k: v for k, v in ssot_input_schema.items() 
                          if k not in ('type', 'required', 'examples')}
        ssot_required = [k for k, v in ssot_properties.items() 
                        if v.get('required', False)]
    
    # Check each vendor field
    for field_name, vendor_field in vendor_schema.items():
        if field_name not in ssot_properties:
            diffs.append(f"❌ Field '{field_name}' missing in SSOT properties")
            continue
        
        ssot_field = ssot_properties[field_name]
        
        # Check required flag
        vendor_required = vendor_field.get('required', False)
        ssot_required_flag = field_name in ssot_required
        if vendor_required != ssot_required_flag:
            diffs.append(f"❌ Field '{field_name}'.required: vendor={vendor_required}, SSOT={ssot_required_flag}")
        
        # Check max_length
        vendor_max_length = vendor_field.get('max_length')
        ssot_max_length = ssot_field.get('max_length')
        if vendor_max_length and vendor_max_length != ssot_max_length:
            diffs.append(f"❌ Field '{field_name}'.max_length: vendor={vendor_max_length}, SSOT={ssot_max_length}")
        
        # Check enum
        vendor_enum = vendor_field.get('enum')
        ssot_enum = ssot_field.get('enum')
        if vendor_enum and ssot_enum:
            vendor_enum_set = set(vendor_enum)
            ssot_enum_set = set(ssot_enum)
            if vendor_enum_set != ssot_enum_set:
                diffs.append(f"❌ Field '{field_name}'.enum: vendor={sorted(vendor_enum)}, SSOT={sorted(ssot_enum)}")
        
        # Check default
        vendor_default = vendor_field.get('default')
        ssot_default = ssot_field.get('default')
        if vendor_default and vendor_default != ssot_default:
            diffs.append(f"❌ Field '{field_name}'.default: vendor={vendor_default}, SSOT={ssot_default}")
    
    # Check pricing (informational)
    vendor_pricing = vendor_doc.get('pricing', {})
    ssot_pricing = ssot_model.get('pricing', {})
    if vendor_pricing and ssot_pricing:
        vendor_credits = vendor_pricing.get('credits')
        ssot_credits = ssot_pricing.get('credits_per_gen')
        if vendor_credits and ssot_credits and vendor_credits != ssot_credits:
            diffs.append(f"⚠️ Pricing.credits: vendor={vendor_credits}, SSOT={ssot_credits} (informational)")
    
    return diffs


def main():
    """Main entry point."""
    vendor_docs_dir = project_root / 'kb' / 'vendor_docs'
    
    if len(sys.argv) >= 2:
        # Check specific file
        doc_path = Path(sys.argv[1])
        if not doc_path.exists():
            print(f"❌ Vendor doc not found: {doc_path}")
            sys.exit(1)
        doc_files = [doc_path]
    else:
        # Check all files in kb/vendor_docs/
        if not vendor_docs_dir.exists():
            print(f"⚠️ Vendor docs directory not found: {vendor_docs_dir}")
            print("   No vendor docs to check.")
            sys.exit(0)
        
        doc_files = list(vendor_docs_dir.glob("*.md"))
        if not doc_files:
            print(f"⚠️ No vendor docs found in {vendor_docs_dir}")
            sys.exit(0)
    
    ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
    if not ssot_path.exists():
        print(f"❌ SSOT file not found: {ssot_path}")
        sys.exit(1)
    
    # Load SSOT
    ssot = load_source_of_truth()
    
    print(f"\n📄 Comparing vendor docs vs SSOT")
    print("=" * 80)
    
    all_diffs = {}
    all_matches = []
    
    for doc_path in doc_files:
        # Parse vendor doc
        vendor_doc = parse_vendor_doc(doc_path)
        if not vendor_doc:
            print(f"⚠️ Failed to parse: {doc_path.name}")
            continue
        
        model_id = vendor_doc.get('model_id')
        print(f"\n📋 {model_id} ({doc_path.name})")
        
        # Compare
        diffs = compare_with_ssot(vendor_doc, ssot)
        
        if diffs:
            all_diffs[model_id] = diffs
            print(f"  ❌ {len(diffs)} difference(s) found:")
            for diff in diffs:
                print(f"    {diff}")
        else:
            all_matches.append(model_id)
            print(f"  ✅ MATCH - No differences found")
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ MATCHES: {len(all_matches)}")
    if all_matches:
        for model_id in all_matches:
            print(f"  - {model_id}")
    
    print(f"❌ DIFFERENCES: {len(all_diffs)}")
    if all_diffs:
        for model_id, diffs in all_diffs.items():
            print(f"  - {model_id}: {len(diffs)} difference(s)")
    
    if all_diffs:
        print("\n💡 To fix: Update SSOT manually or use recommended patches.")
        print("   This script does NOT auto-mutate SSOT.")
        sys.exit(1)
    else:
        print("\n✅ All vendor docs match SSOT perfectly")
        sys.exit(0)


if __name__ == '__main__':
    main()

