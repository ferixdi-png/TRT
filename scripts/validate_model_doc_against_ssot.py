#!/usr/bin/env python3
"""
Validate vendor documentation against SSOT (Source of Truth).

Usage:
    python scripts/validate_model_doc_against_ssot.py <model_id> [doc_path]

If doc_path not provided, looks for kb/vendor_docs/<model_id>.md

Outputs diff report but does NOT mutate SSOT.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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
    
    # Extract output media type
    output_match = re.search(r'Output media type:\s*(\w+)', content, re.IGNORECASE)
    output_media_type = output_match.group(1).lower() if output_match else None
    
    return {
        'model_id': model_id,
        'input_schema': input_schema,
        'output_media_type': output_media_type
    }


def load_ssot(ssot_path: Path) -> Dict[str, Any]:
    """Load SSOT JSON file."""
    if not ssot_path.exists():
        return {}
    
    with open(ssot_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compare_schema(vendor_doc: Dict[str, Any], ssot: Dict[str, Any], model_id: str) -> List[str]:
    """
    Compare vendor doc schema against SSOT and return list of differences.
    
    Returns:
        List of diff messages (empty if match)
    """
    diffs = []
    
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
    ssot_input = ssot_input_schema.get('input', {})
    ssot_properties = ssot_input.get('properties', {})
    
    # If no properties, SSOT only has examples
    if not ssot_properties:
        diffs.append("⚠️ SSOT missing 'properties' structure in input_schema.input (only has examples)")
        # Still check what we can from examples
        if 'examples' in ssot_input:
            examples = ssot_input.get('examples', [])
            if examples and isinstance(examples[0], dict):
                example_fields = set(examples[0].keys())
                vendor_fields = set(vendor_schema.keys())
                missing_in_ssot = vendor_fields - example_fields
                if missing_in_ssot:
                    diffs.append(f"⚠️ Fields in vendor doc but not in SSOT examples: {missing_in_ssot}")
    else:
        # Check each vendor field
        for field_name, vendor_field in vendor_schema.items():
            if field_name not in ssot_properties:
                diffs.append(f"❌ Field '{field_name}' missing in SSOT properties")
                continue
            
            ssot_field = ssot_properties[field_name]
            
            # Check required flag
            vendor_required = vendor_field.get('required', False)
            ssot_required = field_name in ssot_input.get('required', [])
            if vendor_required != ssot_required:
                diffs.append(f"❌ Field '{field_name}'.required: vendor={vendor_required}, SSOT={ssot_required}")
            
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
    
    # Check output media type (category)
    vendor_output = vendor_doc.get('output_media_type')
    if vendor_output:
        ssot_category = ssot_model.get('category', '')
        # Map output_media_type to category
        category_map = {
            'video': 'video',
            'image': 'image',
            'audio': 'audio',
            'text': 'text'
        }
        expected_category = category_map.get(vendor_output, vendor_output)
        if ssot_category != expected_category:
            diffs.append(f"❌ Category: vendor={expected_category} (from output_media_type={vendor_output}), SSOT={ssot_category}")
    
    return diffs


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_model_doc_against_ssot.py <model_id> [doc_path]")
        sys.exit(1)
    
    model_id = sys.argv[1]
    doc_path = None
    
    if len(sys.argv) >= 3:
        doc_path = Path(sys.argv[2])
    else:
        # Default: look in kb/vendor_docs/
        doc_path = project_root / 'kb' / 'vendor_docs' / f"{model_id.replace('/', '-')}.md"
    
    ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
    
    if not doc_path.exists():
        print(f"❌ Vendor doc not found: {doc_path}")
        sys.exit(1)
    
    if not ssot_path.exists():
        print(f"❌ SSOT file not found: {ssot_path}")
        sys.exit(1)
    
    # Parse vendor doc
    vendor_doc = parse_vendor_doc(doc_path)
    if not vendor_doc:
        print(f"❌ Failed to parse vendor doc: {doc_path}")
        sys.exit(1)
    
    # Load SSOT
    ssot = load_ssot(ssot_path)
    
    # Compare
    print(f"\n📄 Comparing vendor doc vs SSOT for: {model_id}")
    print("=" * 80)
    
    diffs = compare_schema(vendor_doc, ssot, model_id)
    
    if diffs:
        print("\n❌ DIFFERENCES FOUND:")
        for diff in diffs:
            print(f"  {diff}")
        print(f"\n⚠️  Found {len(diffs)} difference(s)")
        print("\n💡 To fix: Update SSOT manually or use recommended patches.")
        sys.exit(1)
    else:
        print("\n✅ MATCH - No differences found")
        print("✅ Vendor doc matches SSOT perfectly")
        sys.exit(0)


if __name__ == '__main__':
    main()

