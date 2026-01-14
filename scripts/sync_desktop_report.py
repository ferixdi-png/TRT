#!/usr/bin/env python3
"""
Sync TRT_REPORT.md from repo to Desktop mirror.
Called automatically after each task completion.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_desktop_path() -> Path:
    """Get Desktop path for current OS."""
    if os.name == 'nt':  # Windows
        desktop = Path(os.getenv('USERPROFILE', '')) / 'Desktop'
    else:  # macOS/Linux
        desktop = Path.home() / 'Desktop'
    
    # Fallback if Desktop doesn't exist
    if not desktop.exists():
        desktop = Path.home() / '_desktop'
        desktop.mkdir(exist_ok=True)
    
    return desktop


def sync_report(quiet: bool = False) -> int:
    """
    Sync TRT_REPORT.md from repo to Desktop.
    
    Args:
        quiet: If True, suppress output (for post-commit hook)
    
    Returns:
        0 on success, 1 on error
    """
    repo_report = project_root / 'TRT_REPORT.md'
    desktop = get_desktop_path()
    desktop_report = desktop / 'TRT_REPORT.md'
    
    if not repo_report.exists():
        if not quiet:
            print(f"❌ Repo report not found: {repo_report}")
        return 1
    
    try:
        # Read repo version
        with open(repo_report, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Write to Desktop
        with open(desktop_report, 'w', encoding='utf-8') as f:
            f.write(content)
        
        if not quiet:
            print(f"✅ Synced TRT_REPORT.md to {desktop_report}")
        return 0
    except Exception as e:
        if not quiet:
            print(f"❌ Failed to sync report: {e}")
        return 1


def append_changelog_entry(
    what: str,
    why: str,
    how_tested: str,
    files_changed: list,
    commit_hashes: list,
    deploy_status: str = "pending"
):
    """Append a changelog entry to TRT_REPORT.md."""
    repo_report = project_root / 'TRT_REPORT.md'
    desktop = get_desktop_path()
    desktop_report = desktop / 'TRT_REPORT.md'
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    entry = f"""
---

## Changelog Entry: {what}

**Timestamp**: {timestamp}  
**Why**: {why}  
**How Tested**: {how_tested}  
**Files Changed**: {', '.join(files_changed)}  
**Commits**: {', '.join(commit_hashes)}  
**Deploy Status**: {deploy_status}

"""
    
    # Append to repo version
    try:
        with open(repo_report, 'a', encoding='utf-8') as f:
            f.write(entry)
        print(f"✅ Appended changelog to {repo_report}")
    except Exception as e:
        print(f"⚠️  Failed to append to repo report: {e}")
    
    # Sync to Desktop
    sync_report()
    
    return 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Sync TRT_REPORT.md to Desktop")
    parser.add_argument("--append", action="store_true", help="Append changelog entry")
    parser.add_argument("--what", help="What was changed")
    parser.add_argument("--why", help="Why it was changed")
    parser.add_argument("--how-tested", help="How it was tested")
    parser.add_argument("--files", nargs="+", help="Files changed")
    parser.add_argument("--commits", nargs="+", help="Commit hashes")
    parser.add_argument("--deploy-status", default="pending", help="Deploy status")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (for hooks)")
    
    args = parser.parse_args()
    
    if args.append:
        if not all([args.what, args.why, args.how_tested, args.files, args.commits]):
            print("❌ --append requires --what, --why, --how-tested, --files, --commits")
            sys.exit(1)
        exit_code = append_changelog_entry(
            args.what,
            args.why,
            args.how_tested,
            args.files,
            args.commits,
            args.deploy_status
        )
        # After appending, sync to Desktop
        if exit_code == 0:
            sync_report(quiet=args.quiet)
    else:
        exit_code = sync_report(quiet=args.quiet)
    
    sys.exit(exit_code)

