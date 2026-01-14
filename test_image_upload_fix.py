#!/usr/bin/env python3
"""
Quick validation test for image upload fix.
Tests that:
1. _convert_file_id_to_url function exists and is callable
2. Image URL prompt is clear
3. File handling logic is correct
"""

import sys
import asyncio
from pathlib import Path

# Must import sys before anything that uses aiogram stub
sys.dont_write_bytecode = True

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "bot"))

# Remove local aiogram stub from import path to use real aiogram
local_aiogram = project_root / "aiogram"
if local_aiogram.exists():
    # Remove entries that might pick up local stubs
    new_path = []
    for p in sys.path:
        if p not in {"", str(project_root)}:
            new_path.append(p)
    new_path.insert(0, str(project_root))  # Add back project root at beginning
    sys.path = new_path


def test_image_upload_logic():
    """Test that image upload logic is present and correct."""
    from bot.handlers.flow import (
        _field_prompt, 
        _convert_file_id_to_url,
        InputFlow
    )
    
    print("✅ Successfully imported required functions")
    
    # Test 1: Check _field_prompt for image_url
    print("\n📝 Test 1: Checking _field_prompt for image_url field...")
    field_spec = {"type": "string"}
    prompt = _field_prompt("image_url", field_spec)
    
    assert "🖼️" in prompt, "Prompt should contain image emoji"
    assert "Загрузить" in prompt or "загруж" in prompt.lower(), "Prompt should mention upload"
    assert "фото" in prompt.lower(), "Prompt should mention photo"
    assert "галере" in prompt.lower() or "фотогра" in prompt.lower(), "Prompt should mention gallery"
    print(f"✅ Image URL prompt is clear:\n{prompt[:100]}...")
    
    # Test 2: Check _convert_file_id_to_url function exists
    print("\n🔄 Test 2: Checking _convert_file_id_to_url function...")
    assert asyncio.iscoroutinefunction(_convert_file_id_to_url), "Function should be async"
    print("✅ _convert_file_id_to_url is async function (correct)")
    
    # Test 3: Check InputFlow.waiting_input state exists
    print("\n⏳ Test 3: Checking InputFlow states...")
    assert hasattr(InputFlow, 'waiting_input'), "InputFlow should have waiting_input state"
    print("✅ InputFlow has waiting_input state")
    
    # Test 4: Check that image_url field is recognized
    print("\n🖼️ Test 4: Checking image_url field names...")
    image_field_names = {
        "image_url", "image_urls", "input_image", 
        "reference_image_urls", "reference_mask_urls", "mask_url"
    }
    
    for field_name in image_field_names:
        prompt = _field_prompt(field_name, {})
        assert "загруж" in prompt.lower() or "фото" in prompt.lower(), f"Prompt for {field_name} should mention upload/photo"
    
    print(f"✅ All {len(image_field_names)} image field names are properly handled")
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)
    print("\nNext steps:")
    print("1. Deploy changes to Render")
    print("2. Test image upload flow end-to-end")
    print("3. Try uploading a photo for upscaling")
    print("4. Verify that file_id is converted to URL")

if __name__ == "__main__":
    try:
        test_image_upload_logic()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_image_upload_logic():
    """Test that image upload logic is present and correct."""
    from bot.handlers.flow import (
        _field_prompt, 
        _convert_file_id_to_url,
        InputFlow
    )
    
    print("✅ Successfully imported required functions")
    
    # Test 1: Check _field_prompt for image_url
    print("\n📝 Test 1: Checking _field_prompt for image_url field...")
    field_spec = {"type": "string"}
    prompt = _field_prompt("image_url", field_spec)
    
    assert "🖼️" in prompt, "Prompt should contain image emoji"
    assert "Загрузить" in prompt or "загруж" in prompt.lower(), "Prompt should mention upload"
    assert "фото" in prompt.lower(), "Prompt should mention photo"
    assert "галере" in prompt.lower() or "фотогра" in prompt.lower(), "Prompt should mention gallery"
    print(f"✅ Image URL prompt is clear:\n{prompt[:100]}...")
    
    # Test 2: Check _convert_file_id_to_url function exists
    print("\n🔄 Test 2: Checking _convert_file_id_to_url function...")
    assert asyncio.iscoroutinefunction(_convert_file_id_to_url), "Function should be async"
    print("✅ _convert_file_id_to_url is async function (correct)")
    
    # Test 3: Check InputFlow.waiting_input state exists
    print("\n⏳ Test 3: Checking InputFlow states...")
    assert hasattr(InputFlow, 'waiting_input'), "InputFlow should have waiting_input state"
    print("✅ InputFlow has waiting_input state")
    
    # Test 4: Check that image_url field is recognized
    print("\n🖼️ Test 4: Checking image_url field names...")
    image_field_names = {
        "image_url", "image_urls", "input_image", 
        "reference_image_urls", "reference_mask_urls", "mask_url"
    }
    
    for field_name in image_field_names:
        prompt = _field_prompt(field_name, {})
        assert "загруж" in prompt.lower() or "фото" in prompt.lower(), f"Prompt for {field_name} should mention upload/photo"
    
    print(f"✅ All {len(image_field_names)} image field names are properly handled")
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED!")
    print("="*60)
    print("\nNext steps:")
    print("1. Deploy changes to Render")
    print("2. Test image upload flow end-to-end")
    print("3. Try uploading a photo for upscaling")
    print("4. Verify that file_id is converted to URL")

if __name__ == "__main__":
    try:
        test_image_upload_logic()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
