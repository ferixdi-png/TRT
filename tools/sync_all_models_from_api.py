#!/usr/bin/env python3
"""
Автоматическая синхронизация всех моделей из KIE API в kie_models.py
"""

import os
import sys
import json
import asyncio
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

try:
    from dotenv import load_dotenv
    env_path = root_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def fetch_all_models():
    """Fetch all models from KIE API"""
    try:
        from kie_client import get_client
        
        client = get_client()
        models = await client.list_models()
        
        if not models:
            logger.error("No models returned from API")
            return []
        
        logger.info(f"✅ Fetched {len(models)} models from API")
        return models
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}", exc_info=True)
        return []


def load_current_models():
    """Load current models from kie_models.py"""
    try:
        from kie_models import KIE_MODELS
        return {m.get("id"): m for m in KIE_MODELS if m.get("id")}
    except Exception as e:
        logger.error(f"Failed to load kie_models: {e}")
        return {}


def api_model_to_kie_model(api_model: dict) -> dict:
    """Convert API model to kie_models.py format"""
    model_id = api_model.get("id") or api_model.get("model_id") or api_model.get("name", "")
    
    # Determine category and emoji
    category = "Фото"
    emoji = "🖼️"
    model_id_lower = model_id.lower()
    
    if any(kw in model_id_lower for kw in ["video", "sora", "kling", "wan", "hailuo", "seedance"]):
        category = "Видео"
        emoji = "🎬"
    elif any(kw in model_id_lower for kw in ["audio", "sound", "speech", "music", "suno", "elevenlabs"]):
        category = "Аудио"
        emoji = "🎵"
    
    # Build input_params from API model structure
    input_params = {}
    
    # Try to get input schema from API model
    input_schema = api_model.get("input_schema") or api_model.get("schema") or {}
    
    # If no schema, create basic prompt parameter
    if not input_schema:
        input_params["prompt"] = {
            "type": "string",
            "required": True,
            "max_length": 5000
        }
    else:
        for field_name, field_spec in input_schema.items():
            if isinstance(field_spec, dict):
                param = {"type": field_spec.get("type", "string")}
                if "required" in field_spec:
                    param["required"] = field_spec["required"]
                if "max_length" in field_spec or "max_len" in field_spec:
                    param["max_length"] = field_spec.get("max_length") or field_spec.get("max_len")
                if "enum" in field_spec or "values" in field_spec:
                    param["enum"] = field_spec.get("enum") or field_spec.get("values")
                if "default" in field_spec:
                    param["default"] = field_spec["default"]
                input_params[field_name] = param
    
    return {
        "id": model_id,
        "name": api_model.get("name") or api_model.get("title") or model_id.replace("/", " ").title(),
        "description": api_model.get("description") or f"Модель {model_id}",
        "category": category,
        "emoji": emoji,
        "pricing": "Цена по запросу",
        "input_params": input_params
    }


def generate_model_code(kie_model: dict) -> str:
    """Generate Python code for model entry"""
    code = "    {\n"
    code += f'        "id": {json.dumps(kie_model["id"])},\n'
    code += f'        "name": {json.dumps(kie_model["name"])},\n'
    code += f'        "description": {json.dumps(kie_model["description"])},\n'
    code += f'        "category": {json.dumps(kie_model["category"])},\n'
    code += f'        "emoji": {json.dumps(kie_model["emoji"])},\n'
    code += f'        "pricing": {json.dumps(kie_model["pricing"])},\n'
    code += '        "input_params": {\n'
    
    for param_name, param_spec in kie_model["input_params"].items():
        code += f'            {json.dumps(param_name)}: {{\n'
        code += f'                "type": {json.dumps(param_spec.get("type", "string"))},\n'
        if "required" in param_spec:
            code += f'                "required": {param_spec["required"]},\n'
        if "max_length" in param_spec:
            code += f'                "max_length": {param_spec["max_length"]},\n'
        if "enum" in param_spec:
            code += f'                "enum": {json.dumps(param_spec["enum"], ensure_ascii=False)},\n'
        if "default" in param_spec:
            code += f'                "default": {json.dumps(param_spec["default"], ensure_ascii=False)},\n'
        code += "            },\n"
    
    code += "        }\n"
    code += "    },\n"
    return code


async def main():
    """Main function"""
    logger.info("🚀 Starting automatic model sync from KIE API...")
    
    # Fetch models from API
    api_models = await fetch_all_models()
    if not api_models:
        logger.error("❌ No models fetched, exiting")
        return 1
    
    # Load current models
    current_models = load_current_models()
    logger.info(f"Current models in kie_models.py: {len(current_models)}")
    
    # Find missing models
    missing_models = []
    for api_model in api_models:
        model_id = api_model.get("id") or api_model.get("model_id") or api_model.get("name", "")
        if not model_id or model_id in current_models:
            continue
        missing_models.append(api_model)
        logger.info(f"Missing model: {model_id}")
    
    if not missing_models:
        logger.info("✅ All models already in kie_models.py")
        return 0
    
    logger.info(f"📝 Adding {len(missing_models)} new models...")
    
    # Load kie_models.py
    kie_models_path = Path("kie_models.py")
    if not kie_models_path.exists():
        logger.error("kie_models.py not found")
        return 1
    
    content = kie_models_path.read_text(encoding="utf-8")
    
    # Find insertion point (before closing bracket)
    if "] # end KIE_MODELS" in content:
        insert_pos = content.rfind("] # end KIE_MODELS")
        prefix = content[:insert_pos]
        suffix = "\n] # end KIE_MODELS" + content[insert_pos+len("] # end KIE_MODELS"):]
    elif "\n]" in content[content.find("KIE_MODELS = ["):]:
        insert_pos = content.rfind("\n]")
        prefix = content[:insert_pos]
        suffix = "\n]" + content[insert_pos+2:]
    else:
        logger.error("Could not find end of KIE_MODELS list")
        return 1
    
    # Generate new model entries
    new_models_code = []
    for api_model in missing_models:
        kie_model = api_model_to_kie_model(api_model)
        model_code = generate_model_code(kie_model)
        new_models_code.append(model_code)
    
    # Insert new models
    new_content = prefix + "".join(new_models_code) + suffix
    
    # Write back
    kie_models_path.write_text(new_content, encoding="utf-8")
    logger.info(f"✅ Successfully added {len(missing_models)} models to kie_models.py")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)



