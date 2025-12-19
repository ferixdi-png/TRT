"""
CLI for KIE Market Synchronizer
Usage:
  python -m kie_sync.cli discover
  python -m kie_sync.cli sync [--dry-run] [--model MODEL_ID]
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kie_sync import discover


def main():
    parser = argparse.ArgumentParser(description="KIE Market Synchronizer")
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Discover command
    discover_parser = subparsers.add_parser('discover', help='Discover JSON endpoints and data structures')
    discover_parser.add_argument('--model', help='Specific model slug to discover')
    
    # Sync command (placeholder for now)
    sync_parser = subparsers.add_parser('sync', help='Sync pricing and schemas from KIE Market')
    sync_parser.add_argument('--dry-run', action='store_true', help='Show what would change without modifying files')
    sync_parser.add_argument('--model', help='Sync specific model only')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'discover':
        import asyncio
        asyncio.run(discover.main())
    elif args.command == 'sync':
        from kie_sync import sync
        import asyncio
        asyncio.run(sync.main(dry_run=args.dry_run, model_filter=args.model))


if __name__ == "__main__":
    main()
