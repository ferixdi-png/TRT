#!/usr/bin/env python3
"""
Step 2: Add logging calls inside handlers.
Follows the pattern from flow.py:
1. log_callback_received + log_callback_routed at start
2. log_callback_rejected for early rejections (db_service, etc)
3. log_callback_accepted + log_ui_render at end
"""
import re
from pathlib import Path

# Mapping callback_data patterns to ButtonIds (expand as needed)
CALLBACK_TO_BUTTON = {
    "history:main": "HISTORY_MAIN",
    "history:gallery": "HISTORY_GALLERY",
    "history:transactions": "HISTORY_TRANSACTIONS",
    "marketing:promo": "MARKETING_PROMO",
    "marketing:referral": "MARKETING_REFERRAL",
    "marketing:bonus": "MARKETING_BONUS",
    "quick:menu": "QUICK_MENU",
    "gallery:show": "GALLERY_SHOW",
    "gallery:detail": "GALLERY_DETAIL",
}

# Mapping callback_data to ScreenIds
CALLBACK_TO_SCREEN = {
    "history:main": "HISTORY_LIST",
    "history:gallery": "HISTORY_GALLERY",
    "history:transactions": "HISTORY_TRANSACTIONS",
    "marketing:promo": "MARKETING_PROMO",
    "marketing:referral": "MARKETING_REFERRAL",
    "marketing:bonus": "MARKETING_BONUS",
    "quick:menu": "QUICK_MENU",
    "gallery:show": "GALLERY_SHOW",
}


def extract_callback_data(decorator: str) -> str | None:
    """Extract callback_data from decorator."""
    # Match: @router.callback_query(F.data == "something")
    match = re.search(r'F\.data\s*==\s*["\']([^"\']+)["\']', decorator)
    if match:
        return match.group(1)
    
    # Match: @router.callback_query(F.data.startswith("something"))
    match = re.search(r'F\.data\.startswith\(["\']([^"\']+)["\']', decorator)
    if match:
        return match.group(1)
    
    return None


def add_logging_to_handler(file_path: Path, dry_run=False) -> tuple[bool, str]:
    """
    Add logging calls to handlers.
    Returns (changed, message).
    """
    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # Find handlers with cid parameter
    handler_pattern = re.compile(
        r'@router\.callback_query\([^)]+\)\s*\n'
        r'async def (\w+)\([^)]*cid=None[^)]*\):',
        re.MULTILINE
    )
    
    matches = list(handler_pattern.finditer(content))
    if not matches:
        return False, f"⏭️ {file_path.name}: No handlers with cid parameter"
    
    # Check if already has logging
    if "log_callback_received(" in content:
        return False, f"✅ {file_path.name}: Already has logging calls"
    
    # For each handler, find decorator and insert logging
    modified = False
    
    for match in matches:
        func_name = match.group(1)
        func_start = match.start()
        
        # Find decorator line (backward search)
        decorator_line_idx = None
        for idx, line in enumerate(lines):
            if f"async def {func_name}(" in line:
                decorator_line_idx = idx - 1
                break
        
        if decorator_line_idx is None:
            continue
        
        decorator = lines[decorator_line_idx]
        callback_data = extract_callback_data(decorator)
        
        if not callback_data:
            continue
        
        button_id = CALLBACK_TO_BUTTON.get(callback_data, "UNKNOWN")
        screen_id = CALLBACK_TO_SCREEN.get(callback_data, "UNKNOWN")
        
        # Find function body start (after docstring)
        func_line_idx = decorator_line_idx + 1
        body_start_idx = func_line_idx + 1
        
        # Skip docstring if present
        if body_start_idx < len(lines) and '"""' in lines[body_start_idx]:
            # Find end of docstring
            for idx in range(body_start_idx + 1, len(lines)):
                if '"""' in lines[idx]:
                    body_start_idx = idx + 1
                    break
        
        # Insert user_id/chat_id extraction
        indent = "    "
        insert_lines = [
            f"{indent}user_id = callback.from_user.id",
            f"{indent}chat_id = callback.message.chat.id",
            "",
            f"{indent}if cid:",
            f'{indent}    log_callback_received(cid, callback.id, user_id, chat_id, "{callback_data}", bot_state)',
            f'{indent}    log_callback_routed(cid, user_id, chat_id, "{func_name}", "{callback_data}", ButtonId.{button_id})',
            "",
        ]
        
        lines[body_start_idx:body_start_idx] = insert_lines
        modified = True
    
    if modified and not dry_run:
        file_path.write_text("\n".join(lines), encoding="utf-8")
        return True, f"✨ {file_path.name}: Added logging to {len(matches)} handlers"
    
    return modified, f"✨ {file_path.name}: Would add logging to {len(matches)} handlers (dry run)"


def main():
    handlers_dir = Path(__file__).parent.parent / "bot" / "handlers"
    
    files_to_process = [
        "history.py",
        "marketing.py",
        "quick_actions.py",
        "gallery.py",
    ]
    
    results = []
    
    for file_name in files_to_process:
        file_path = handlers_dir / file_name
        if not file_path.exists():
            results.append((False, f"❌ {file_name}: Not found"))
            continue
        
        try:
            changed, msg = add_logging_to_handler(file_path)
            results.append((changed, msg))
        except Exception as e:
            results.append((False, f"❌ {file_name}: {e}"))
    
    # Print results
    print("\n" + "="*60)
    print("LOGGING INJECTION RESULTS")
    print("="*60 + "\n")
    
    for changed, msg in results:
        print(msg)
    
    changed_count = sum(1 for c, _ in results if c)
    print(f"\n{'='*60}")
    print(f"Total: {changed_count} files modified")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
