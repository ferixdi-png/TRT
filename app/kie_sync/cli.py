"""
CLI for Kie sync commands.

Commands:
- kie-sync pull   -> fetch pages, cache HTML
- kie-sync build  -> build normalized upstream JSON
- kie-sync reconcile -> merge into local registry
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from app.kie_sync.config import UPSTREAM_JSON_PATH, GENERATED_DIR
from app.kie_sync.parser import KieParser
from app.kie_sync.reconciler import KieReconciler

logging = None
try:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
except:
    pass


async def cmd_pull(use_cache: bool = True):
    """Pull: fetch pages and cache HTML."""
    print("📥 Pulling Kie.ai documentation pages...")
    
    async with KieParser() as parser:
        # Discover pages
        pages = await parser.discover_pages()
        print(f"  Found {len(pages)} pages")
        
        # Fetch each page
        results = []
        for i, url in enumerate(pages, 1):
            print(f"  [{i}/{len(pages)}] Fetching {url}...")
            try:
                data = await parser.parse_page(url, use_cache=use_cache)
                if data:
                    results.append(data)
                    print(f"    ✅ {data['model_id']}")
                else:
                    print(f"    ⚠️  Failed to parse")
            except Exception as e:
                print(f"    ❌ Error: {e}")
        
        print(f"\n✅ Pulled {len(results)} models")
        return results


async def cmd_build(use_cache: bool = True):
    """Build: create normalized upstream JSON."""
    print("🔨 Building normalized upstream JSON...")
    
    async with KieParser() as parser:
        # Discover and parse pages
        pages = await parser.discover_pages()
        print(f"  Found {len(pages)} pages")
        
        models = {}
        for i, url in enumerate(pages, 1):
            print(f"  [{i}/{len(pages)}] Parsing {url}...")
            try:
                data = await parser.parse_page(url, use_cache=use_cache)
                if data and data.get("model_id"):
                    model_id = data["model_id"]
                    models[model_id] = data
                    print(f"    ✅ {model_id}")
                else:
                    print(f"    ⚠️  Failed to parse")
            except Exception as e:
                print(f"    ❌ Error: {e}")
        
        # Build upstream JSON
        upstream = {
            "version": "1.0.0",
            "source": "kie_upstream",
            "models": models,
            "_metadata": {
                "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_models": len(models)
            }
        }
        
        # Write to file
        UPSTREAM_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(UPSTREAM_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(upstream, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ Built upstream JSON: {len(models)} models")
        print(f"   Saved to: {UPSTREAM_JSON_PATH}")
        return upstream


def cmd_reconcile(dry_run: bool = False):
    """Reconcile: merge upstream into local registry."""
    print("🔄 Reconciling upstream data with local SOURCE_OF_TRUTH...")
    
    reconciler = KieReconciler()
    diff = reconciler.reconcile(dry_run=dry_run)
    
    print(f"\n📊 Diff Report:")
    print(f"  Added models: {len(diff['added_models'])}")
    if diff['added_models']:
        for model_id in diff['added_models']:
            print(f"    + {model_id}")
    
    print(f"  Changed models: {len(diff['changed_models'])}")
    if diff['changed_models']:
        for model_id in diff['changed_models']:
            print(f"    ~ {model_id}")
            if model_id in diff['new_fields']:
                print(f"      New fields: {', '.join(diff['new_fields'][model_id])}")
    
    print(f"  New fields: {sum(len(fields) for fields in diff['new_fields'].values())}")
    
    if dry_run:
        print("\n⚠️  DRY RUN - no files were modified")
    else:
        print("\n✅ Reconciliation complete")
    
    return diff


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: kie-sync <command> [options]")
        print("\nCommands:")
        print("  pull       - Fetch pages and cache HTML")
        print("  build      - Build normalized upstream JSON")
        print("  reconcile  - Merge upstream into local registry")
        print("\nOptions:")
        print("  --no-cache  - Don't use cache (force fetch)")
        print("  --no-write  - Dry run (don't write files)")
        sys.exit(1)
    
    command = sys.argv[1]
    use_cache = "--no-cache" not in sys.argv
    dry_run = "--no-write" in sys.argv
    
    try:
        if command == "pull":
            asyncio.run(cmd_pull(use_cache=use_cache))
        elif command == "build":
            asyncio.run(cmd_build(use_cache=use_cache))
        elif command == "reconcile":
            cmd_reconcile(dry_run=dry_run)
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if logger:
            logger.exception("CLI error")
        sys.exit(1)


if __name__ == "__main__":
    main()

