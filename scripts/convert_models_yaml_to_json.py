#!/usr/bin/env python3
"""
Convert models/kie_models.yaml to models/kie_api_models.json format.

The YAML file contains 72 models with detailed input specifications.
We convert to a flattened JSON API format compatible with kie_builder.py
"""

import json
import yaml
from pathlib import Path
from typing import Any, Dict, List

def get_pricing_for_model(model_id: str) -> Dict[str, Any]:
    """Get default pricing structure for a model."""
    # Default pricing (can be adjusted per model type)
    pricing_map = {
        "text_to_image": {"credits_per_gen": 10.0, "kie_price_rub": 5.0, "our_price_rub": 12.0},
        "image_to_image": {"credits_per_gen": 15.0, "kie_price_rub": 7.5, "our_price_rub": 18.0},
        "text_to_video": {"credits_per_gen": 30.0, "kie_price_rub": 15.0, "our_price_rub": 36.0},
        "image_to_video": {"credits_per_gen": 30.0, "kie_price_rub": 15.0, "our_price_rub": 36.0},
        "video_to_video": {"credits_per_gen": 40.0, "kie_price_rub": 20.0, "our_price_rub": 48.0},
    }
    return pricing_map.get("text_to_image", {"credits_per_gen": 10.0, "kie_price_rub": 5.0, "our_price_rub": 12.0})

def convert_input_schema(model_id: str, yaml_input: Dict[str, Any]) -> Dict[str, Any]:
    """Convert YAML input specification to JSON schema format."""
    properties = {}
    required = []
    
    for param_name, param_spec in yaml_input.items():
        prop_type = param_spec.get("type", "string")
        
        # Build property schema
        prop = {
            "type": prop_type,
            "description": f"Parameter {param_name} for {model_id}"
        }
        
        # Add constraints
        if "max" in param_spec:
            prop["max_length"] = param_spec["max"]
        
        if "values" in param_spec:
            prop["enum"] = param_spec["values"]
        
        if param_spec.get("required", False):
            required.append(param_name)
        
        properties[param_name] = prop
    
    return {
        "required": required,
        "properties": properties
    }

def convert_yaml_to_json() -> Dict[str, Any]:
    """Convert YAML models to JSON API format."""
    yaml_path = Path(__file__).parent.parent / "models" / "kie_models.yaml"
    
    with open(yaml_path) as f:
        yaml_data = yaml.safe_load(f)
    
    models_list = []
    yaml_models = yaml_data.get("models", {})
    
    for model_id, model_config in yaml_models.items():
        model_type = model_config.get("model_type", "text_to_image")
        
        # Build display name
        display_name = model_id.replace("-", " ").replace("/", " ").title()
        
        # Get pricing
        pricing = get_pricing_for_model(model_id)
        
        # Convert input schema
        input_yaml = model_config.get("input", {})
        input_schema = convert_input_schema(model_id, input_yaml)
        
        model_entry = {
            "model_id": model_id,
            "display_name": display_name,
            "category": model_type.replace("_", "-"),
            "modality": model_type.replace("_", "-"),
            "provider": "Kie.ai",
            "pricing": {
                "credits_per_gen": pricing.get("credits_per_gen", 10.0),
                "kie_price_usd": pricing.get("kie_price_rub", 5.0) / 100,  # Rough estimate
                "kie_price_rub": pricing.get("kie_price_rub", 5.0),
                "our_price_rub": pricing.get("our_price_rub", 12.0),
                "markup_percent": round((pricing.get("our_price_rub", 12.0) / pricing.get("kie_price_rub", 5.0) - 1) * 100)
            },
            "input_schema": input_schema
        }
        
        models_list.append(model_entry)
    
    return {
        "version": "6.0.0",
        "source": "kie_models.yaml",
        "generated_at": "2026-01-11",
        "api_endpoint": "/api/v1/jobs/createTask",
        "polling_endpoint": "/api/v1/jobs/recordInfo",
        "models": models_list
    }

def main():
    """Main entry point."""
    print("[*] Converting models/kie_models.yaml to kie_api_models.json...")
    
    json_data = convert_yaml_to_json()
    
    output_path = Path(__file__).parent.parent / "models" / "kie_api_models.json"
    
    with open(output_path, "w") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"[✓] Converted {len(json_data['models'])} models")
    print(f"[✓] Saved to {output_path}")
    
    # Print summary
    model_types = {}
    for m in json_data["models"]:
        mt = m["modality"]
        model_types[mt] = model_types.get(mt, 0) + 1
    
    print("\nModel types breakdown:")
    for mt, count in sorted(model_types.items()):
        print(f"  - {mt}: {count} models")

if __name__ == "__main__":
    main()
