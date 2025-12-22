#!/usr/bin/env python3
"""
Generate artifacts/models/source.json showing which source was used for models
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

# Add project root to path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.models.registry import load_models, get_model_registry


async def main():
    """Generate source.json artifact"""
    # Load models (this will try API first, then fallback)
    models = await load_models(force_refresh=True)
    registry_info = get_model_registry()
    
    # Create artifact
    artifact = {
        "used_source": registry_info.get("used_source", "unknown"),
        "count": len(models),
        "timestamp": datetime.now().isoformat(),
        "sample_ids": [m.get('id', '') for m in models[:10]] if models else [],
        "api_available": os.getenv('KIE_API_KEY') is not None,
        "api_url": os.getenv('KIE_API_URL', 'https://api.kie.ai')
    }
    
    # Save artifact
    artifact_dir = root_dir / "artifacts" / "models"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = artifact_dir / "source.json"
    
    with open(artifact_file, 'w', encoding='utf-8') as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Generated {artifact_file}")
    print(f"   Source: {artifact['used_source']}")
    print(f"   Count: {artifact['count']}")
    print(f"   Sample IDs: {artifact['sample_ids'][:5]}")


if __name__ == "__main__":
    asyncio.run(main())
