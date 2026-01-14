#!/usr/bin/env python3
"""
Fetch raw Render logs and save to artifacts/ directory.
Used for before/after comparison.
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.render_logs_check import load_render_config, fetch_render_logs


def main():
    """Fetch and save raw logs."""
    # Create artifacts directory
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    
    # Load config
    config = load_render_config()
    if not config:
        print("❌ Config not loaded")
        return 1
    
    api_key = config.get("RENDER_API_KEY")
    service_id = config.get("RENDER_SERVICE_ID")
    
    if not api_key or not service_id:
        print("❌ RENDER_API_KEY or RENDER_SERVICE_ID missing")
        return 1
    
    # Fetch logs
    print(f"📥 Fetching logs for service {service_id}...")
    logs = fetch_render_logs(api_key, service_id, minutes=60)
    
    if not logs:
        print("⚠️  No logs fetched")
        return 0
    
    # Save with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = artifacts_dir / f"render_logs_before_{timestamp}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(logs))
    
    print(f"✅ Saved {len(logs)} log lines to {output_file}")
    
    # Analyze for summary
    errors = [line for line in logs if 'error' in line.lower() or 'exception' in line.lower() or 'traceback' in line.lower()]
    import_errors = [line for line in logs if 'import' in line.lower() and 'error' in line.lower()]
    
    print(f"\n📊 Summary:")
    print(f"  Total lines: {len(logs)}")
    print(f"  Errors/Exceptions: {len(errors)}")
    print(f"  Import Errors: {len(import_errors)}")
    
    if import_errors:
        print(f"\n⚠️  Import Errors found:")
        for i, err in enumerate(import_errors[:5], 1):
            print(f"  {i}. {err[:100]}")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

