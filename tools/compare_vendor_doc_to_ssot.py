#!/usr/bin/env python3
"""
Compare vendor documentation to SSOT (Source of Truth).

This script parses vendor docs (from kb/vendor_docs/*.md) and compares
them against the SSOT (models/KIE_SOURCE_OF_TRUTH.json).

Outputs a diff report but does NOT auto-mutate SSOT.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = None
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
    
    # Extract endpoints
    endpoints_match = re.search(r'Endpoints:\s*([^\n]+)', content, re.IGNORECASE)
    endpoints = []
    if endpoints_match:
        endpoints_text = endpoints_match.group(1)
        # Parse POST/GET endpoints
        for method in ['POST', 'GET', 'PUT', 'DELETE']:
            if method in endpoints_text:
                endpoint_match = re.search(rf'{method}\s+([^\s,]+)', endpoints_text)
                if endpoint_match:
                    endpoints.append({
                        'method': method,
                        'path': endpoint_match.group(1)
                    })
    
    # Extract input schema
    schema_section = re.search(r'Input schema:([^\n]+(?:\n(?!Pricing:)[^\n]+)*)', content, re.IGNORECASE | re.MULTILINE)
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
                default = default_match.group(1).strip()
            
            input_schema[field_name] = {
                'type': field_type,
                'required': required,
                'max_length': max_length,
                'max_items': max_items,
                'enum': enum_values,
                'default': default
            }
    
    # Extract pricing
    pricing_section = re.search(r'Pricing:([^\n]+(?:\n[^\n]+)*)', content, re.IGNORECASE | re.MULTILINE)
    pricing = {}
    if pricing_section:
        pricing_text = pricing_section.group(1)
        # Parse pricing rules
        # Format: - X credits for Y (flat) or - X credits for Y, Z credits for W
        pricing_rules = {}
        resolution_match = re.search(r'(\d+)\s+credits\s+for\s+(\d+K)', pricing_text, re.IGNORECASE)
        if resolution_match:
            credits = int(resolution_match.group(1))
            resolution = resolution_match.group(2)
            pricing_rules['resolution'] = {resolution: credits}
        
        # Check for multiple resolution tiers
        all_resolution_matches = re.finditer(r'(\d+)\s+credits\s+for\s+(\d+K)', pricing_text, re.IGNORECASE)
        if all_resolution_matches:
            resolution_map = {}
            for match in all_resolution_matches:
                credits = int(match.group(1))
                resolution = match.group(2)
                resolution_map[resolution] = credits
            if resolution_map:
                pricing_rules['resolution'] = resolution_map
                pricing_rules['strategy'] = 'by_resolution'
    
    return {
        'model_id': model_id,
        'endpoints': endpoints,
        'input_schema': input_schema,
        'pricing': pricing
    }


def load_ssot(ssot_path: Path) -> Dict[str, Any]:
    """Load SSOT JSON file."""
    if not ssot_path.exists():
        return {}
    
    with open(ssot_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compare_model(vendor_doc: Dict[str, Any], ssot: Dict[str, Any]) -> List[str]:
    """
    Compare vendor doc against SSOT and return list of differences.
    
    Returns:
        List of diff messages (empty if match)
    """
    diffs = []
    model_id = vendor_doc['model_id']
    
    if 'models' not in ssot:
        diffs.append(f"SSOT has no 'models' key")
        return diffs
    
    if model_id not in ssot['models']:
        diffs.append(f"Model '{model_id}' not found in SSOT")
        return diffs
    
    ssot_model = ssot['models'][model_id]
    
    # Compare endpoints
    ssot_endpoint = ssot_model.get('endpoint', '')
    vendor_endpoints = vendor_doc.get('endpoints', [])
    if vendor_endpoints:
        vendor_create_endpoint = next((e['path'] for e in vendor_endpoints if e['method'] == 'POST'), None)
        if vendor_create_endpoint and vendor_create_endpoint not in ssot_endpoint:
            diffs.append(f"Endpoint mismatch: vendor={vendor_create_endpoint}, SSOT={ssot_endpoint}")
    
    # Compare input schema
    vendor_schema = vendor_doc.get('input_schema', {})
    ssot_input_schema = ssot_model.get('input_schema', {})
    ssot_input = ssot_input_schema.get('input', {})
    ssot_properties = ssot_input.get('properties', {})
    
    # Check each vendor field
    for field_name, vendor_field in vendor_schema.items():
        if field_name not in ssot_properties:
            diffs.append(f"Field '{field_name}' missing in SSOT")
            continue
        
        ssot_field = ssot_properties[field_name]
        
        # Check required flag
        vendor_required = vendor_field.get('required', False)
        ssot_required = field_name in ssot_input.get('required', [])
        if vendor_required != ssot_required:
            diffs.append(f"Field '{field_name}' required mismatch: vendor={vendor_required}, SSOT={ssot_required}")
        
        # Check max_length
        vendor_max_length = vendor_field.get('max_length')
        ssot_max_length = ssot_field.get('max_length')
        if vendor_max_length and vendor_max_length != ssot_max_length:
            diffs.append(f"Field '{field_name}' max_length mismatch: vendor={vendor_max_length}, SSOT={ssot_max_length}")
        
        # Check enum
        vendor_enum = vendor_field.get('enum')
        ssot_enum = ssot_field.get('enum')
        if vendor_enum and ssot_enum:
            vendor_enum_set = set(vendor_enum)
            ssot_enum_set = set(ssot_enum)
            if vendor_enum_set != ssot_enum_set:
                diffs.append(f"Field '{field_name}' enum mismatch: vendor={vendor_enum}, SSOT={ssot_enum}")
        
        # Check default
        vendor_default = vendor_field.get('default')
        ssot_default = ssot_field.get('default')
        if vendor_default and vendor_default != ssot_default:
            diffs.append(f"Field '{field_name}' default mismatch: vendor={vendor_default}, SSOT={ssot_default}")
    
    # Compare pricing
    vendor_pricing = vendor_doc.get('pricing', {})
    ssot_pricing = ssot_model.get('pricing', {})
    
    if vendor_pricing.get('pricing_rules'):
        vendor_rules = vendor_pricing['pricing_rules']
        ssot_rules = ssot_pricing.get('pricing_rules', {})
        
        if vendor_rules.get('resolution'):
            vendor_res = vendor_rules['resolution']
            ssot_res = ssot_rules.get('resolution', {})
            
            for res_key, vendor_credits in vendor_res.items():
                ssot_credits = ssot_res.get(res_key)
                if ssot_credits != vendor_credits:
                    diffs.append(f"Pricing rule resolution '{res_key}' mismatch: vendor={vendor_credits} credits, SSOT={ssot_credits} credits")
    
    return diffs


def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    vendor_docs_dir = project_root / 'kb' / 'vendor_docs'
    ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
    
    if not vendor_docs_dir.exists():
        print(f"❌ Vendor docs directory not found: {vendor_docs_dir}")
        return 1
    
    if not ssot_path.exists():
        print(f"❌ SSOT file not found: {ssot_path}")
        return 1
    
    # Load SSOT
    ssot = load_ssot(ssot_path)
    
    # Process all vendor docs
    vendor_doc_files = list(vendor_docs_dir.glob('*.md'))
    if not vendor_doc_files:
        print(f"⚠️  No vendor doc files found in {vendor_docs_dir}")
        return 0
    
    all_diffs = {}
    for doc_path in vendor_doc_files:
        model_name = doc_path.stem
        print(f"\n📄 Processing: {model_name}")
        
        vendor_doc = parse_vendor_doc(doc_path)
        if not vendor_doc:
            print(f"  ⚠️  Failed to parse vendor doc")
            continue
        
        diffs = compare_model(vendor_doc, ssot)
        if diffs:
            all_diffs[model_name] = diffs
            print(f"  ❌ Found {len(diffs)} differences:")
            for diff in diffs:
                print(f"     - {diff}")
        else:
            print(f"  ✅ MATCH - No differences found")
    
    # Summary
    print(f"\n{'='*60}")
    if all_diffs:
        print(f"❌ SUMMARY: {len(all_diffs)} model(s) have differences")
        print(f"\nTo fix, update SSOT manually or use recommended patches below:")
        for model_name, diffs in all_diffs.items():
            print(f"\n  Model: {model_name}")
            for diff in diffs:
                print(f"    - {diff}")
        return 1
    else:
        print(f"✅ SUMMARY: All vendor docs match SSOT")
        return 0


if __name__ == '__main__':
    sys.exit(main())

