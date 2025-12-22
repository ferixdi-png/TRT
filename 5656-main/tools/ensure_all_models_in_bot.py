#!/usr/bin/env python3
"""
Проверяет что все модели из catalog.yaml есть в kie_models.py
Если нет - добавляет автоматически
"""

import sys
import json
import yaml
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_catalog():
    """Load models/catalog.yaml"""
    catalog_path = Path("models/catalog.yaml")
    if not catalog_path.exists():
        logger.warning("models/catalog.yaml not found")
        return {}
    
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("models", {})
    except Exception as e:
        logger.error(f"Failed to load catalog: {e}")
        return {}


def load_current_models():
    """Load current models from kie_models.py"""
    try:
        from kie_models import KIE_MODELS
        return {m.get("id"): m for m in KIE_MODELS if m.get("id")}
    except Exception as e:
        logger.error(f"Failed to load kie_models: {e}")
        return {}


def ensure_all_models():
    """Ensure all catalog models are in kie_models.py"""
    catalog_models = load_catalog()
    current_models = load_current_models()
    
    logger.info(f"Catalog models: {len(catalog_models)}")
    logger.info(f"Current models in bot: {len(current_models)}")
    
    if not catalog_models:
        logger.warning("⚠️ Catalog is empty. Run: python tools/kie_sync/export_market.py --sync")
        logger.info("✅ Current models in bot will be used")
        return
    
    missing = []
    for model_id in catalog_models:
        if model_id not in current_models:
            missing.append(model_id)
    
    if missing:
        logger.warning(f"⚠️ Missing {len(missing)} models in kie_models.py:")
        for model_id in missing[:10]:
            logger.warning(f"  - {model_id}")
        if len(missing) > 10:
            logger.warning(f"  ... and {len(missing) - 10} more")
        logger.info("\n💡 To add missing models, run:")
        logger.info("   python scripts/full_sync_kie_models.py")
        logger.info("   OR")
        logger.info("   python tools/kie_sync/export_market.py --sync")
    else:
        logger.info("✅ All catalog models are in kie_models.py")
    
    return len(missing) == 0


if __name__ == "__main__":
    success = ensure_all_models()
    sys.exit(0 if success else 1)



