#!/usr/bin/env python3
"""
Auto-integrate telemetry into all callback handlers.
Follows the pattern from flow.py and z_image.py.
"""
import re
import sys
from pathlib import Path

TELEMETRY_IMPORTS = """from app.telemetry.telemetry_helpers import (
    log_callback_received, log_callback_routed, log_callback_accepted,
    log_callback_rejected, log_ui_render
)
from app.telemetry.logging_contract import ReasonCode
from app.telemetry.ui_registry import ScreenId, ButtonId"""


def has_telemetry(content: str) -> bool:
    """Check if file already has telemetry imports."""
    return "from app.telemetry.telemetry_helpers import" in content


def add_imports(content: str) -> str:
    """Add telemetry imports after aiogram imports."""
    if has_telemetry(content):
        return content
    
    # Find last aiogram import
    lines = content.split("\n")
    last_import_idx = -1
    
    for idx, line in enumerate(lines):
        if line.startswith("from aiogram") or line.startswith("import aiogram"):
            last_import_idx = idx
    
    if last_import_idx == -1:
        # No aiogram imports found, insert after all imports
        for idx, line in enumerate(lines):
            if not line.startswith(("import ", "from ")) and line.strip():
                last_import_idx = idx - 1
                break
    
    # Insert telemetry imports
    lines.insert(last_import_idx + 1, "")
    lines.insert(last_import_idx + 2, TELEMETRY_IMPORTS)
    
    return "\n".join(lines)


def integrate_handler(file_path: Path) -> tuple[bool, str]:
    """
    Integrate telemetry into a handler file.
    Returns (changed, message).
    """
    content = file_path.read_text(encoding="utf-8")
    
    # Check if already integrated
    if "cid=None, bot_state=None" in content:
        return False, f"✅ {file_path.name}: Already integrated"
    
    # Add imports
    content = add_imports(content)
    
    # Pattern for callback handler without cid parameter
    # Match: async def handler_name(callback: CallbackQuery, ...)
    # Where ... can be state, other params, but NOT cid
    handler_pattern = re.compile(
        r'(@router\.callback_query\([^)]+\)\s*\n'
        r'async def (\w+)\(callback: CallbackQuery(?:,\s*state:\s*FSMContext)?)(\s*,\s*[^)]+)?\)\s*(?:->.*?)?:',
        re.MULTILINE
    )
    
    matches = list(handler_pattern.finditer(content))
    
    if not matches:
        return False, f"⏭️ {file_path.name}: No callback handlers found"
    
    # Process handlers in reverse to maintain positions
    for match in reversed(matches):
        decorator, func_name, existing_params = match.group(1), match.group(2), match.group(3) or ""
        
        # Skip if already has cid parameter
        if "cid" in existing_params:
            continue
        
        # Build new signature
        base_sig = f"callback: CallbackQuery"
        if ", state:" in match.group(0):
            base_sig += ", state: FSMContext"
        
        new_sig = f"{base_sig}, cid=None, bot_state=None"
        
        # Replace signature
        old_sig_pattern = re.compile(
            rf'async def {func_name}\(callback: CallbackQuery(?:,\s*state:\s*FSMContext)?{re.escape(existing_params)}\)',
            re.MULTILINE
        )
        
        content = old_sig_pattern.sub(
            f'async def {func_name}({new_sig})',
            content,
            count=1
        )
    
    # Save changes
    file_path.write_text(content, encoding="utf-8")
    
    return True, f"✨ {file_path.name}: Integrated {len(matches)} handlers"


def main():
    handlers_dir = Path(__file__).parent.parent / "bot" / "handlers"
    
    if not handlers_dir.exists():
        print(f"❌ Handlers directory not found: {handlers_dir}")
        sys.exit(1)
    
    # Skip certain files
    skip_files = {
        "__init__.py",
        "error_handler.py",  # Global error handler, different pattern
        "zero_silence.py",   # Special case
        "diag.py",           # Debug handler
        "admin_router.py",   # Old/deprecated
    }
    
    results = []
    
    for file_path in sorted(handlers_dir.glob("*.py")):
        if file_path.name in skip_files:
            continue
        
        try:
            changed, msg = integrate_handler(file_path)
            results.append((changed, msg))
        except Exception as e:
            results.append((False, f"❌ {file_path.name}: {e}"))
    
    # Print results
    print("\n" + "="*60)
    print("TELEMETRY INTEGRATION RESULTS")
    print("="*60 + "\n")
    
    for changed, msg in results:
        print(msg)
    
    changed_count = sum(1 for c, _ in results if c)
    print(f"\n{'='*60}")
    print(f"Total: {changed_count} files modified")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
