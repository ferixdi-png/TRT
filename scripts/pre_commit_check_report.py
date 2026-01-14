#!/usr/bin/env python3
"""
Pre-commit check: ensures TRT_REPORT.md is updated when app/ or bot/ files change.

Exit code:
- 0: OK (either no app/bot changes, or TRT_REPORT.md was updated)
- 1: FAIL (app/bot changed but TRT_REPORT.md not updated)
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_staged_files() -> List[str]:
    """Get list of staged files (relative to repo root)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return []


def get_changed_files_in_commit() -> List[str]:
    """Get list of files changed in current commit (for CI/post-commit checks)."""
    try:
        # Get files changed in HEAD commit
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return []


def has_app_or_bot_changes(files: List[str]) -> bool:
    """Check if any staged files are in app/ or bot/ directories."""
    for file in files:
        if file.startswith("app/") or file.startswith("bot/"):
            return True
    return False


def is_report_updated(files: List[str]) -> bool:
    """Check if TRT_REPORT.md is in the list of changed files."""
    return "TRT_REPORT.md" in files


def main():
    """Main pre-commit check."""
    # Get staged files (for pre-commit hook)
    staged_files = get_staged_files()
    
    # Also check HEAD commit (for CI/post-commit)
    commit_files = get_changed_files_in_commit()
    
    # Combine both lists (for comprehensive check)
    all_changed_files = list(set(staged_files + commit_files))
    
    if not all_changed_files:
        # No changes, nothing to check
        print("ℹ️  No files changed, skipping TRT_REPORT.md check")
        return 0
    
    # Check if app/ or bot/ files changed
    has_app_bot_changes = has_app_or_bot_changes(all_changed_files)
    
    if not has_app_bot_changes:
        # No app/bot changes, no need to update report
        print("✅ No app/ or bot/ files changed, TRT_REPORT.md check skipped")
        return 0
    
    # App/bot files changed - check if TRT_REPORT.md was updated
    report_updated = is_report_updated(all_changed_files)
    
    if report_updated:
        print("✅ TRT_REPORT.md is updated (app/bot changes detected)")
        return 0
    else:
        print("=" * 60)
        print("❌ PRE-COMMIT CHECK FAILED")
        print("=" * 60)
        print("")
        print("Files in app/ or bot/ were changed, but TRT_REPORT.md was not updated.")
        print("")
        print("Changed app/bot files:")
        for file in all_changed_files:
            if file.startswith("app/") or file.startswith("bot/"):
                print(f"  - {file}")
        print("")
        print("ACTION REQUIRED:")
        print("  1. Update TRT_REPORT.md with a changelog entry")
        print("  2. Stage TRT_REPORT.md: git add TRT_REPORT.md")
        print("  3. Try committing again")
        print("")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Pre-commit check error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

