#!/usr/bin/env python3
"""
Precise diff: vendor-doc vs SSOT for bytedance/v1-pro-fast-image-to-video.
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
        "max_length": 10000
    },
    "image_url": {
        "required": True,
        "type": "string",
        "max_size_mb": 10,
        "formats": ["jpeg", "png", "webp"]
    },
    "resolution": {
        "required": False,
        "type": "enum",
        "default": "720p",
        "enum": ["720p", "1080p"]
    },
    "duration": {
        "required": False,
        "type": "enum",
        "default": "5",
        "enum": ["5", "10"]
    },
    "output_media_type": "video"
}

# Load SSOT
ssot_path = project_root / 'models' / 'KIE_SOURCE_OF_TRUTH.json'
with open(ssot_path, 'r', encoding='utf-8') as f:
    ssot = json.load(f)

model = ssot['models']['bytedance/v1-pro-fast-image-to-video']
ssot_input = model['input_schema'].get('input', {})
ssot_properties = ssot_input.get('properties', {})

print("=" * 80)
print("PRECISE DIFF: vendor-doc vs SSOT for bytedance/v1-pro-fast-image-to-video")
print("=" * 80)

diffs = []
matches = []

# Check if properties structure exists
if not ssot_properties:
    diffs.append("❌ SSOT missing 'properties' structure in input_schema.input")
    print("\n⚠️  SSOT has no properties structure - only examples")
    print("   Need to add properties structure with required/optional flags, defaults, enums")
else:
    # Compare each field
    for field_name, vendor_spec in vendor_doc.items():
        if field_name == "output_media_type":
            # Check category instead
            ssot_category = model.get('category', '')
            if ssot_category != 'video':
                diffs.append(f"❌ Category: vendor=video, SSOT={ssot_category}")
            else:
                matches.append(f"✅ Category: video")
            continue
        
        if field_name not in ssot_properties:
            diffs.append(f"❌ Field '{field_name}': MISSING in SSOT properties")
            continue
        
        ssot_field = ssot_properties[field_name]
        
        # Check required
        vendor_required = vendor_spec.get('required', False)
        ssot_required = field_name in ssot_input.get('required', [])
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

# Check category
ssot_category = model.get('category', '')
if ssot_category != 'video':
    diffs.append(f"❌ Category: vendor=video (image-to-video model), SSOT={ssot_category}")

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

