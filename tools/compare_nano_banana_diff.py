#!/usr/bin/env python3
"""
Precise diff: vendor-doc vs SSOT for nano-banana-pro.
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

# Vendor doc specs
vendor_doc = {
    "prompt": {
        "required": True,
        "type": "string",
        "max_length": 20000
    },
    "image_input": {
        "required": False,
        "type": "array",
        "max_items": 8,
        "item_type": "URL",
        "formats": ["jpeg", "png", "webp"],
        "max_size_mb": 30
    },
    "aspect_ratio": {
        "required": False,
        "type": "enum",
        "default": "1:1",
        "enum": ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"]
    },
    "resolution": {
        "required": False,
        "type": "enum",
        "default": "1K",
        "enum": ["1K", "2K", "4K"]
    },
    "output_format": {
        "required": False,
        "type": "enum",
        "default": "png",
        "enum": ["png", "jpg"]
    },
    "pricing": {
        "1K": 18,
        "2K": 18,
        "4K": 24
    }
}

# Load SSOT
ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
with open(ssot_path, 'r', encoding='utf-8') as f:
    ssot = json.load(f)

model = ssot['models']['nano-banana-pro']
ssot_schema = model['input_schema']['input']['properties']
ssot_pricing = model['pricing'].get('pricing_rules', {}).get('resolution', {})

print("=" * 80)
print("PRECISE DIFF: vendor-doc vs SSOT for nano-banana-pro")
print("=" * 80)

diffs = []
matches = []

# Compare each field
for field_name, vendor_spec in vendor_doc.items():
    if field_name == "pricing":
        continue
    
    if field_name not in ssot_schema:
        diffs.append(f"❌ Field '{field_name}': MISSING in SSOT")
        continue
    
    ssot_field = ssot_schema[field_name]
    
    # Check required
    vendor_required = vendor_spec.get('required', False)
    ssot_required = field_name in model['input_schema']['input'].get('required', [])
    if vendor_required != ssot_required:
        diffs.append(f"❌ Field '{field_name}'.required: vendor={vendor_required}, SSOT={ssot_required}")
    else:
        matches.append(f"✅ Field '{field_name}'.required: {vendor_required}")
    
    # Check max_length
    if 'max_length' in vendor_spec:
        vendor_max = vendor_spec['max_length']
        ssot_max = ssot_field.get('max_length')
        if vendor_max != ssot_max:
            diffs.append(f"❌ Field '{field_name}'.max_length: vendor={vendor_max}, SSOT={ssot_max}")
        else:
            matches.append(f"✅ Field '{field_name}'.max_length: {vendor_max}")
    
    # Check max_items
    if 'max_items' in vendor_spec:
        vendor_max = vendor_spec['max_items']
        ssot_max = ssot_field.get('max_items')
        if vendor_max != ssot_max:
            diffs.append(f"❌ Field '{field_name}'.max_items: vendor={vendor_max}, SSOT={ssot_max}")
        else:
            matches.append(f"✅ Field '{field_name}'.max_items: {vendor_max}")
    
    # Check default
    if 'default' in vendor_spec:
        vendor_default = vendor_spec['default']
        ssot_default = ssot_field.get('default')
        if vendor_default != ssot_default:
            diffs.append(f"❌ Field '{field_name}'.default: vendor={vendor_default}, SSOT={ssot_default}")
        else:
            matches.append(f"✅ Field '{field_name}'.default: {vendor_default}")
    
    # Check enum
    if 'enum' in vendor_spec:
        vendor_enum = set(vendor_spec['enum'])
        ssot_enum = set(ssot_field.get('enum', []))
        if vendor_enum != ssot_enum:
            diffs.append(f"❌ Field '{field_name}'.enum: vendor={sorted(vendor_enum)}, SSOT={sorted(ssot_enum)}")
        else:
            matches.append(f"✅ Field '{field_name}'.enum: {sorted(vendor_enum)}")

# Compare pricing
vendor_pricing = vendor_doc['pricing']
for res, credits in vendor_pricing.items():
    ssot_credits = ssot_pricing.get(res)
    if ssot_credits != credits:
        diffs.append(f"❌ Pricing.resolution['{res}']: vendor={credits}, SSOT={ssot_credits}")
    else:
        matches.append(f"✅ Pricing.resolution['{res}']: {credits} credits")

# Summary
print("\n" + "=" * 80)
print("MATCHES:")
print("=" * 80)
for match in matches:
    print(f"  {match}")

print("\n" + "=" * 80)
print("DIFFERENCES:")
print("=" * 80)
if diffs:
    for diff in diffs:
        print(f"  {diff}")
    print(f"\n❌ Found {len(diffs)} difference(s)")
    sys.exit(1)
else:
    print("  ✅ No differences found - vendor doc matches SSOT")
    print(f"\n✅ All {len(matches)} fields match")
    sys.exit(0)

