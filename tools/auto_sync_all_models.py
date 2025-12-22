#!/usr/bin/env python3
"""
Автоматическая синхронизация всех моделей из KIE Market в бот.
1. Синхронизирует catalog.yaml и pricing/config.yaml из KIE Market
2. Обновляет kie_models.py на основе catalog.yaml
"""

import os
import sys
import json
import yaml
from pathlib import Path

# Add root to path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to load .env
try:
    from dotenv import load_dotenv
    env_path = root_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def load_catalog() -> dict:
    """Load models/catalog.yaml"""
    catalog_path = Path("models/catalog.yaml")
    if not catalog_path.exists():
        logger.warning("models/catalog.yaml not found, creating empty")
        return {"meta": {"source": "kie.ai/market"}, "models": {}}
    
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"models": {}}
    except Exception as e:
        logger.error(f"Failed to load catalog: {e}")
        return {"models": {}}


def load_current_models() -> dict:
    """Load current models from kie_models.py"""
    try:
        from kie_models import KIE_MODELS
        return {m.get("id"): m for m in KIE_MODELS if m.get("id")}
    except Exception as e:
        logger.error(f"Failed to load kie_models: {e}")
        return {}


def catalog_to_kie_model(catalog_entry: dict, model_id: str) -> dict:
    """Convert catalog entry to kie_models.py format"""
    schema = catalog_entry.get("input_schema", {})
    
    # Build input_params
    input_params = {}
    for field_name, field_spec in schema.items():
        if isinstance(field_spec, dict) and field_spec.get("unsupported"):
            continue
        
        param = {
            "type": field_spec.get("type", "string"),
        }
        
        if "required" in field_spec:
            param["required"] = field_spec["required"]
        if "max_len" in field_spec:
            param["max_length"] = field_spec["max_len"]
        if "max_length" in field_spec:
            param["max_length"] = field_spec["max_length"]
        if "values" in field_spec:
            param["enum"] = field_spec["values"]
        if "default" in field_spec:
            param["default"] = field_spec["default"]
        
        input_params[field_name] = param
    
    # Determine category from model_id
    category = "Фото"
    emoji = "🖼️"
    if any(kw in model_id.lower() for kw in ["video", "sora", "kling", "wan", "hailuo", "seedance"]):
        category = "Видео"
        emoji = "🎬"
    elif any(kw in model_id.lower() for kw in ["audio", "sound", "speech", "music", "suno", "elevenlabs"]):
        category = "Аудио"
        emoji = "🎵"
    
    return {
        "id": model_id,
        "name": catalog_entry.get("title", model_id.replace("/", " ").title()),
        "description": f"Модель {model_id}",
        "category": category,
        "emoji": emoji,
        "pricing": "Цена по запросу",
        "input_params": input_params
    }


def sync_models_from_catalog():
    """Sync models from catalog.yaml to kie_models.py"""
    catalog = load_catalog()
    current_models = load_current_models()
    catalog_models = catalog.get("models", {})
    
    logger.info(f"Catalog models: {len(catalog_models)}")
    logger.info(f"Current models: {len(current_models)}")
    
    # Find missing models
    missing_models = []
    for model_id, catalog_entry in catalog_models.items():
        if model_id not in current_models:
            missing_models.append((model_id, catalog_entry))
            logger.info(f"Missing model: {model_id}")
    
    if not missing_models:
        logger.info("✅ All models already in kie_models.py")
        return
    
    # Load kie_models.py file
    kie_models_path = Path("kie_models.py")
    if not kie_models_path.exists():
        logger.error("kie_models.py not found")
        return
    
    content = kie_models_path.read_text(encoding="utf-8")
    
    # Find KIE_MODELS list
    if "KIE_MODELS = [" not in content:
        logger.error("KIE_MODELS list not found in kie_models.py")
        return
    
    # Generate new model entries
    new_models_code = []
    for model_id, catalog_entry in missing_models:
        kie_model = catalog_to_kie_model(catalog_entry, model_id)
        
        # Convert to Python dict format
        model_code = "    {\n"
        model_code += f'        "id": "{kie_model["id"]}",\n'
        model_code += f'        "name": "{kie_model["name"]}",\n'
        model_code += f'        "description": "{kie_model["description"]}",\n'
        model_code += f'        "category": "{kie_model["category"]}",\n'
        model_code += f'        "emoji": "{kie_model["emoji"]}",\n'
        model_code += f'        "pricing": "{kie_model["pricing"]}",\n'
        model_code += '        "input_params": {\n'
        
        for param_name, param_spec in kie_model["input_params"].items():
            model_code += f'            "{param_name}": {{\n'
            model_code += f'                "type": "{param_spec.get("type", "string")}",\n'
            if "required" in param_spec:
                model_code += f'                "required": {param_spec["required"]},\n'
            if "max_length" in param_spec:
                model_code += f'                "max_length": {param_spec["max_length"]},\n'
            if "enum" in param_spec:
                enum_str = json.dumps(param_spec["enum"], ensure_ascii=False)
                model_code += f'                "enum": {enum_str},\n'
            if "default" in param_spec:
                default_str = json.dumps(param_spec["default"], ensure_ascii=False)
                model_code += f'                "default": {default_str},\n'
            model_code += "            },\n"
        
        model_code += "        }\n"
        model_code += "    },\n"
        
        new_models_code.append(model_code)
    
    # Insert before closing bracket
    if "] # end KIE_MODELS" in content:
        insert_pos = content.rfind("] # end KIE_MODELS")
        new_content = content[:insert_pos] + "".join(new_models_code) + "\n] # end KIE_MODELS" + content[insert_pos+len("] # end KIE_MODELS"):]
    elif "\n]" in content[content.find("KIE_MODELS = ["):]:
        insert_pos = content.rfind("\n]")
        new_content = content[:insert_pos] + "".join(new_models_code) + "\n]" + content[insert_pos+2:]
    else:
        logger.error("Could not find end of KIE_MODELS list")
        return
    
    # Write back
    kie_models_path.write_text(new_content, encoding="utf-8")
    logger.info(f"✅ Added {len(missing_models)} new models to kie_models.py")


def main():
    """Main function"""
    logger.info("🚀 Starting automatic model sync...")
    
    # Step 1: Sync from KIE Market (if export_market.py exists)
    export_script = Path("tools/kie_sync/export_market.py")
    if export_script.exists():
        logger.info("Step 1: Syncing from KIE Market...")
        try:
            # Check if storage state exists
            state_path = Path(".cache/kie_storage_state.json")
            cookie_header = os.getenv("KIE_COOKIE_HEADER")
            
            if state_path.exists() or cookie_header:
                import subprocess
                result = subprocess.run(
                    [sys.executable, str(export_script), "--sync", "--limit", "0"],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                if result.returncode == 0:
                    logger.info("✅ KIE Market sync completed")
                else:
                    logger.warning(f"⚠️ KIE Market sync failed: {result.stderr}")
            else:
                logger.warning("⚠️ No KIE auth available, skipping market sync")
        except Exception as e:
            logger.warning(f"⚠️ KIE Market sync error: {e}")
    else:
        logger.info("⚠️ export_market.py not found, skipping market sync")
    
    # Step 2: Sync models from catalog to kie_models.py
    logger.info("Step 2: Syncing models from catalog to kie_models.py...")
    sync_models_from_catalog()
    
    logger.info("✅ Automatic model sync completed")


if __name__ == "__main__":
    main()



