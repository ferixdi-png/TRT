#!/usr/bin/env python3
"""
Validate input defaults vs required parameters for top 5 popular models.

Checks that all parameters (except prompt) are either:
1. Asked from user via UI
2. Have defaults applied

Outputs a table for TRT_REPORT.md.
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Top 5 popular models (based on usage/visibility)
POPULAR_MODELS = [
    "z-image",
    "flux-2/pro-text-to-image",
    "google/imagen4-fast",
    "kling/v2-1-standard",
    "bytedance/v1-pro-fast-image-to-video",
]


def load_source_of_truth() -> Dict[str, Any]:
    """Load KIE_SOURCE_OF_TRUTH.json."""
    sot_path = project_root / "models" / "KIE_SOURCE_OF_TRUTH.json"
    if not sot_path.exists():
        raise FileNotFoundError(f"SOURCE_OF_TRUTH not found: {sot_path}")
    
    with open(sot_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_model_input_schema(model_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract input schema from model data."""
    # SOURCE_OF_TRUTH format: input_schema.input (nested)
    input_schema = model_data.get("input_schema", {})
    
    # Check if it's nested (input_schema.input.properties)
    if "input" in input_schema:
        input_obj = input_schema["input"]
        if isinstance(input_obj, dict) and "properties" in input_obj:
            return input_obj["properties"]
        elif isinstance(input_obj, dict):
            # Flat format
            return input_obj
    
    # Check if it's flat (input_schema.properties)
    if "properties" in input_schema:
        return input_schema["properties"]
    
    # Check if it's already flat
    if all(isinstance(v, dict) and ("type" in v or "required" in v) for v in input_schema.values()):
        return input_schema
    
    return {}


def check_model_defaults(model_id: str) -> Dict[str, Any]:
    """Check if model has defaults defined."""
    try:
        from app.kie.model_defaults import get_model_defaults
        defaults = get_model_defaults(model_id)
        return defaults
    except Exception:
        return {}


def analyze_model_parameters(model_id: str, model_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze model parameters: required vs optional, defaults vs asked.
    
    Returns:
        {
            "model_id": str,
            "display_name": str,
            "parameters": [
                {
                    "name": str,
                    "required": bool,
                    "has_default": bool,
                    "default_value": Any,
                    "type": str,
                    "source": "asked" | "default" | "missing"
                }
            ],
            "issues": List[str]
        }
    """
    input_schema = get_model_input_schema(model_data)
    model_defaults = check_model_defaults(model_id)
    
    display_name = model_data.get("display_name") or model_id
    
    parameters = []
    issues = []
    
    # Analyze each parameter
    for param_name, param_spec in input_schema.items():
        # Skip internal fields
        if param_name in ["model", "callBackUrl"]:
            continue
        
        # Get parameter info
        required = param_spec.get("required", False)
        param_type = param_spec.get("type", "unknown")
        
        # Check for default in schema
        schema_default = param_spec.get("default")
        has_schema_default = schema_default is not None
        
        # Check for default in model_defaults
        has_model_default = param_name in model_defaults
        model_default_value = model_defaults.get(param_name) if has_model_default else None
        
        # Determine source
        if param_name == "prompt":
            source = "asked"  # Prompt is always asked
        elif required and not has_schema_default and not has_model_default:
            source = "missing"
            issues.append(f"Required parameter '{param_name}' has no default and may not be asked")
        elif has_schema_default or has_model_default:
            source = "default"
        else:
            source = "asked"  # Optional without default - should be asked
        
        parameters.append({
            "name": param_name,
            "required": required,
            "has_default": has_schema_default or has_model_default,
            "default_value": schema_default if has_schema_default else model_default_value,
            "type": param_type,
            "source": source,
        })
    
    return {
        "model_id": model_id,
        "display_name": display_name,
        "parameters": parameters,
        "issues": issues,
    }


def generate_report_table(results: List[Dict[str, Any]]) -> str:
    """Generate markdown table for TRT_REPORT.md."""
    lines = [
        "## Input Defaults vs Required: Validation Report",
        "",
        "### Top 5 Popular Models Analysis",
        "",
        "| Model | Parameter | Required | Has Default | Default Value | Source |",
        "|-------|-----------|----------|-------------|---------------|--------|",
    ]
    
    for result in results:
        model_id = result["model_id"]
        display_name = result["display_name"]
        
        if not result["parameters"]:
            lines.append(f"| **{display_name}** | *No parameters found* | - | - | - | - |")
            continue
        
        # First row: model name
        first_param = result["parameters"][0]
        lines.append(
            f"| **{display_name}** | `{first_param['name']}` | "
            f"{'✅' if first_param['required'] else '❌'} | "
            f"{'✅' if first_param['has_default'] else '❌'} | "
            f"{str(first_param['default_value'])[:30] if first_param['default_value'] is not None else '-'} | "
            f"{first_param['source']} |"
        )
        
        # Remaining parameters
        for param in result["parameters"][1:]:
            lines.append(
                f"| | `{param['name']}` | "
                f"{'✅' if param['required'] else '❌'} | "
                f"{'✅' if param['has_default'] else '❌'} | "
                f"{str(param['default_value'])[:30] if param['default_value'] is not None else '-'} | "
                f"{param['source']} |"
            )
        
        # Issues row
        if result["issues"]:
            lines.append(f"| | ⚠️ **Issues:** | | | | |")
            for issue in result["issues"]:
                lines.append(f"| | {issue} | | | | |")
        
        lines.append("| | | | | | |")  # Separator
    
    lines.extend([
        "",
        "### Legend",
        "- **Source**: `asked` = parameter is asked from user, `default` = has default value, `missing` = required but no default",
        "- **Required**: ✅ = required, ❌ = optional",
        "- **Has Default**: ✅ = has default in schema or model_defaults, ❌ = no default",
        "",
        "### Summary",
    ])
    
    # Summary statistics
    total_params = sum(len(r["parameters"]) for r in results)
    asked_params = sum(sum(1 for p in r["parameters"] if p["source"] == "asked") for r in results)
    default_params = sum(sum(1 for p in r["parameters"] if p["source"] == "default") for r in results)
    missing_params = sum(sum(1 for p in r["parameters"] if p["source"] == "missing") for r in results)
    
    lines.extend([
        f"- Total parameters analyzed: {total_params}",
        f"- Parameters asked from user: {asked_params}",
        f"- Parameters with defaults: {default_params}",
        f"- Missing defaults (issues): {missing_params}",
        "",
    ])
    
    return "\n".join(lines)


def main():
    """Main validation function."""
    print("=" * 60)
    print("Input Defaults vs Required: Validation")
    print("=" * 60)
    print()
    
    try:
        sot = load_source_of_truth()
        models_data = sot.get("models", {})
        
        results = []
        
        for model_id in POPULAR_MODELS:
            if model_id not in models_data:
                print(f"⚠️  Model not found: {model_id}")
                continue
            
            print(f"Analyzing: {model_id}...")
            model_data = models_data[model_id]
            result = analyze_model_parameters(model_id, model_data)
            results.append(result)
            
            # Print summary
            print(f"  Parameters: {len(result['parameters'])}")
            print(f"  Issues: {len(result['issues'])}")
            if result["issues"]:
                for issue in result["issues"]:
                    print(f"    - {issue}")
            print()
        
        # Generate report
        report = generate_report_table(results)
        
        # Save to file
        report_path = project_root / "INPUT_DEFAULTS_VALIDATION.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"✅ Report saved to: {report_path}")
        print()
        print(report)
        
        return 0 if all(len(r["issues"]) == 0 for r in results) else 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

