#!/usr/bin/env python3
"""
Sync KIE.ai source of truth (DoD point 11).

Attempts to fetch official model/pricing data from KIE.ai and update SOURCE_OF_TRUTH.

Process:
1. Check for public JSON endpoint (models/pricing API)
2. If available: fetch, validate, update models/KIE_SOURCE_OF_TRUTH.json
3. If auth required: use KIE_API_KEY
4. If HTML-only: return SYNC_UNAVAILABLE + reason (no fragile HTML parsing)
5. Log changes to docs/ or TRT_REPORT.md

Exit codes:
- 0: Sync successful or SYNC_UNAVAILABLE (honest status)
- 1: Sync failed (critical error)

Usage:
    python scripts/sync_kie_truth.py
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94mℹ\033[0m"
WARN = "\033[93m⚠\033[0m"

# KIE API endpoints to try
KIE_API_BASE = os.getenv("KIE_API_URL", "https://api.kie.ai")
POSSIBLE_ENDPOINTS = [
    f"{KIE_API_BASE}/api/v1/models",
    f"{KIE_API_BASE}/v1/models",
    f"{KIE_API_BASE}/models",
    f"{KIE_API_BASE}/api/models",
]


class KieSyncTool:
    def __init__(self):
        self.api_key = os.getenv("KIE_API_KEY")
        self.source_of_truth_path = project_root / "models" / "KIE_SOURCE_OF_TRUTH.json"
        self.changes: list[str] = []
        self.status = "UNKNOWN"
    
    async def attempt_fetch_public_endpoint(self) -> Optional[Dict[str, Any]]:
        """Try to fetch models from public/semi-public endpoints."""
        import aiohttp
        
        print(f"{INFO} Attempting to fetch KIE models from public endpoints...")
        
        for endpoint in POSSIBLE_ENDPOINTS:
            try:
                print(f"  Trying: {endpoint}")
                
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(endpoint, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            content_type = resp.headers.get("Content-Type", "")
                            
                            if "application/json" in content_type:
                                data = await resp.json()
                                print(f"{PASS} Found JSON response at {endpoint}")
                                return data
                            elif "text/html" in content_type:
                                print(f"{WARN} Endpoint returned HTML (web page, not API)")
                                continue
                            else:
                                print(f"{WARN} Unknown content type: {content_type}")
                                continue
                        elif resp.status == 401:
                            print(f"{WARN} 401 Unauthorized (may need valid API key)")
                        elif resp.status == 404:
                            print(f"{WARN} 404 Not Found")
                        else:
                            print(f"{WARN} HTTP {resp.status}")
            except asyncio.TimeoutError:
                print(f"{WARN} Timeout")
            except Exception as e:
                print(f"{WARN} Error: {e}")
        
        return None
    
    def load_current_source_of_truth(self) -> Dict[str, Any]:
        """Load existing SOURCE_OF_TRUTH."""
        if not self.source_of_truth_path.exists():
            print(f"{WARN} SOURCE_OF_TRUTH not found at {self.source_of_truth_path}")
            return {}
        
        with open(self.source_of_truth_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def validate_models_data(self, data: Dict[str, Any]) -> bool:
        """Validate that fetched data has expected structure."""
        # Check if it looks like valid models data
        if isinstance(data, dict):
            # Could be: {"models": {...}} or direct model dict
            if "models" in data:
                models = data["models"]
                if isinstance(models, dict) and len(models) > 0:
                    return True
            elif any(isinstance(v, dict) for v in data.values()):
                # Direct model dict
                return True
        
        return False
    
    def compare_and_update(self, current: Dict[str, Any], fetched: Dict[str, Any]) -> bool:
        """Compare current and fetched data, update if different."""
        # Normalize structure
        current_models = current.get("models", {})
        
        # Determine if fetched has wrapper or is direct dict
        if "models" in fetched:
            fetched_models = fetched["models"]
        else:
            fetched_models = fetched
        
        # Compare model counts
        current_count = len(current_models)
        fetched_count = len(fetched_models)
        
        if current_count != fetched_count:
            self.changes.append(f"Model count changed: {current_count} → {fetched_count}")
        
        # Compare model IDs
        current_ids = set(current_models.keys())
        fetched_ids = set(fetched_models.keys())
        
        added = fetched_ids - current_ids
        removed = current_ids - fetched_ids
        
        if added:
            self.changes.append(f"Added models: {', '.join(sorted(added)[:5])}{'...' if len(added) > 5 else ''}")
        if removed:
            self.changes.append(f"Removed models: {', '.join(sorted(removed)[:5])}{'...' if len(removed) > 5 else ''}")
        
        # If no changes, check if any model data changed
        common_ids = current_ids & fetched_ids
        changed_models = []
        
        for model_id in list(common_ids)[:10]:  # Sample first 10
            if current_models[model_id] != fetched_models.get(model_id):
                changed_models.append(model_id)
        
        if changed_models:
            self.changes.append(f"Updated models: {', '.join(changed_models[:3])}{'...' if len(changed_models) > 3 else ''}")
        
        # If changes detected, update file
        if self.changes:
            new_data = {
                "version": "2.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "models": fetched_models
            }
            
            # Backup current
            backup_path = self.source_of_truth_path.with_suffix(".json.bak")
            if self.source_of_truth_path.exists():
                import shutil
                shutil.copy2(self.source_of_truth_path, backup_path)
                print(f"{INFO} Backed up current to {backup_path}")
            
            # Write new
            with open(self.source_of_truth_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
            
            print(f"{PASS} Updated {self.source_of_truth_path}")
            return True
        else:
            print(f"{INFO} No changes detected")
            return False
    
    def write_sync_report(self, status: str):
        """Write sync report to TRT_REPORT.md."""
        report_path = project_root / "TRT_REPORT.md"
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        sync_section = f"""
---

## KIE.ai TRUTH SYNC STATUS

**Last Sync:** {timestamp}  
**Status:** {status}

"""
        
        if self.changes:
            sync_section += "**Changes Detected:**\n"
            for change in self.changes:
                sync_section += f"- {change}\n"
        else:
            sync_section += "*No changes detected.*\n"
        
        if status == "SYNC_UNAVAILABLE":
            sync_section += """
**Reason:** KIE.ai does not provide public JSON API for models.  
**Update Method:** Manual updates via SOURCE_OF_TRUTH.json  
**Next Steps:** Monitor KIE.ai documentation for API endpoints.
"""
        
        # Append to report if exists
        if report_path.exists():
            content = report_path.read_text()
            
            # Remove old sync section if exists
            if "## KIE.ai TRUTH SYNC STATUS" in content:
                lines = content.split("\n")
                start_idx = None
                end_idx = None
                
                for i, line in enumerate(lines):
                    if "## KIE.ai TRUTH SYNC STATUS" in line:
                        start_idx = i
                    elif start_idx is not None and line.startswith("##") and i > start_idx:
                        end_idx = i
                        break
                
                if start_idx is not None:
                    if end_idx is not None:
                        # Remove old section
                        lines = lines[:start_idx] + lines[end_idx:]
                    else:
                        # Remove to end
                        lines = lines[:start_idx]
                
                content = "\n".join(lines)
            
            # Append new section
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(content.rstrip() + "\n" + sync_section)
            
            print(f"{PASS} Updated {report_path}")
        else:
            print(f"{WARN} TRT_REPORT.md not found, skipping report update")
    
    async def run(self) -> int:
        """Main sync process."""
        print("\n" + "="*70)
        print("KIE.AI SOURCE OF TRUTH SYNC (DoD Point 11)")
        print("="*70 + "\n")
        
        # Step 1: Try to fetch from public endpoints
        fetched_data = await self.attempt_fetch_public_endpoint()
        
        if fetched_data is None:
            # No public endpoint available
            print(f"\n{WARN} SYNC_UNAVAILABLE: No public JSON API found")
            print(f"{INFO} KIE.ai models must be updated manually via SOURCE_OF_TRUTH.json")
            print(f"{INFO} This is not an error - KIE.ai may not provide public model catalog API")
            
            self.status = "SYNC_UNAVAILABLE"
            self.write_sync_report("SYNC_UNAVAILABLE")
            
            return 0  # This is OK
        
        # Step 2: Validate fetched data
        if not self.validate_models_data(fetched_data):
            print(f"\n{FAIL} Fetched data does not have valid model structure")
            self.status = "SYNC_FAILED"
            return 1
        
        print(f"{PASS} Fetched data validated")
        
        # Step 3: Load current SOURCE_OF_TRUTH
        current_data = self.load_current_source_of_truth()
        
        # Step 4: Compare and update
        updated = self.compare_and_update(current_data, fetched_data)
        
        if updated:
            self.status = "SYNC_OK"
            print(f"\n{PASS} SYNC_OK: SOURCE_OF_TRUTH updated")
        else:
            self.status = "SYNC_OK_NO_CHANGES"
            print(f"\n{PASS} SYNC_OK: No changes needed")
        
        # Step 5: Write report
        self.write_sync_report(self.status)
        
        return 0


async def main():
    """Main entry point."""
    tool = KieSyncTool()
    exit_code = await tool.run()
    
    print("\n" + "="*70)
    print(f"Final Status: {tool.status}")
    print("="*70 + "\n")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
