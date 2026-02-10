#!/usr/bin/env python3
"""Audit all models in kie_models.yaml for missing/incomplete parameters."""

import sys
import yaml
from pathlib import Path

# Fix encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8')

def audit_models():
    yaml_path = Path(__file__).parent.parent / "models" / "kie_models.yaml"
    
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    models = data.get("models", {})
    
    issues = []
    
    for model_id, model_def in sorted(models.items()):
        model_type = model_def.get("model_type", "unknown")
        input_params = model_def.get("input", {})
        
        # Check for required params based on model type
        required_by_type = {
            "text_to_image": ["prompt"],
            "image_to_image": ["prompt", "image_input|input_urls|fileUrls|image_urls|source_image"],
            "text_to_video": ["prompt"],
            "image_to_video": ["prompt|text", "image_input|input_urls|fileUrls|image_urls|source_image"],
            "text_to_speech": ["text|prompt"],
            "speech_to_text": ["audio_url|audio|fileUrls"],
            "lip_sync": ["video_url|video|fileUrls", "audio_url|audio"],
            "upscale": ["image_input|input_urls|fileUrls|image_urls"],
            "bg_remove": ["image_input|input_urls|fileUrls|image_urls"],
        }
        
        expected = required_by_type.get(model_type, [])
        param_names = list(input_params.keys())
        
        missing = []
        for req in expected:
            alternatives = req.split("|")
            found = any(alt in param_names for alt in alternatives)
            if not found:
                missing.append(req)
        
        # Count required vs optional
        required_count = sum(1 for p in input_params.values() if isinstance(p, dict) and p.get("required", False))
        optional_count = len(input_params) - required_count
        
        print(f"\n{'='*60}")
        print(f"📦 {model_id}")
        print(f"   Type: {model_type}")
        print(f"   Params: {len(input_params)} ({required_count} required, {optional_count} optional)")
        
        if param_names:
            for pname, pdef in input_params.items():
                if isinstance(pdef, dict):
                    ptype = pdef.get("type", "?")
                    preq = "✅" if pdef.get("required") else "⚪"
                    pvals = pdef.get("values", [])
                    vals_str = f" [{', '.join(str(v) for v in pvals[:3])}{'...' if len(pvals) > 3 else ''}]" if pvals else ""
                    print(f"      {preq} {pname}: {ptype}{vals_str}")
        
        if missing:
            issues.append((model_id, missing))
            print(f"   ⚠️  MISSING: {missing}")
    
    print(f"\n\n{'='*60}")
    print(f"SUMMARY: {len(models)} models, {len(issues)} with potential issues")
    
    if issues:
        print("\nModels with missing params:")
        for model_id, missing in issues:
            print(f"  - {model_id}: {missing}")

if __name__ == "__main__":
    audit_models()
