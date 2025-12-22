"""
Demo: validate input for different models
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kie_schema import validate_input

# Test WAN 2.6
print("=== Test 1: WAN 2.6 (valid) ===")
input1 = {
    "prompt": "A cat walking in Tokyo",
    "duration": "5",
    "resolution": "720p"
}
ok, errors = validate_input("wan/2-6-text-to-video", input1)
print(f"Valid: {ok}")
if errors:
    print(f"Errors: {errors}")

print("\n=== Test 2: WAN 2.6 (invalid duration) ===")
input2 = {
    "prompt": "A cat",
    "duration": "20",  # Invalid
    "resolution": "720p"
}
ok, errors = validate_input("wan/2-6-text-to-video", input2)
print(f"Valid: {ok}")
if errors:
    print(f"Errors: {errors}")

print("\n=== Test 3: WAN 2.6 (missing prompt) ===")
input3 = {
    "duration": "5",
    "resolution": "720p"
}
ok, errors = validate_input("wan/2-6-text-to-video", input3)
print(f"Valid: {ok}")
if errors:
    print(f"Errors: {errors}")

print("\n=== Test 4: WAN 2.6 (with image_url) ===")
input4 = {
    "prompt": "A cat",
    "duration": "5",
    "resolution": "720p",
    "image_urls": ["https://example.com/image.jpg"]
}
ok, errors = validate_input("wan/2-6-text-to-video", input4)
print(f"Valid: {ok}")
if errors:
    print(f"Errors: {errors}")

print("\nSUCCESS: Validation demo complete")
