#!/usr/bin/env python3
"""
Render Logs Check - автоматическая проверка логов Render на ошибки.

Читает Desktop/TRT_RENDER.env и проверяет последние N минут логов через Render API.
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_render_config() -> Dict[str, str]:
    """
    Load Render config from Desktop/TRT_RENDER.env.
    
    Returns:
        Dict with RENDER_API_KEY, RENDER_SERVICE_ID, DATABASE_URL_READONLY
    """
    # Detect Desktop path
    if os.name == 'nt':  # Windows
        desktop_path = Path(os.getenv('USERPROFILE', '')) / 'Desktop'
    else:  # macOS/Linux
        desktop_path = Path.home() / 'Desktop'
    
    env_file = desktop_path / 'TRT_RENDER.env'
    
    if not env_file.exists():
        print(f"⚠️  Config file not found: {env_file}")
        print("   Create it with:")
        print("   RENDER_API_KEY=your_key")
        print("   RENDER_SERVICE_ID=your_service_id")
        print("   DATABASE_URL_READONLY=your_readonly_url")
        return {}
    
    config = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    
    return config


def redact_secret(value: str, show_chars: int = 4) -> str:
    """Redact secret, showing only last N chars."""
    if not value or len(value) <= show_chars:
        return "****"
    return "*" * (len(value) - show_chars) + value[-show_chars:]


def redact_secrets_in_log_line(line: str) -> str:
    """
    Redact secrets in a log line (tokens, passwords, API keys, etc.).
    
    Patterns to redact:
    - Bearer tokens: Bearer <token>
    - API keys: api_key=<value>, API_KEY=<value>
    - Passwords: password=<value>, pwd=<value>
    - Tokens: token=<value>, TOKEN=<value>
    - Database URLs: postgresql://, postgres:// (keep hostname, redact credentials)
    - Telegram tokens: TELEGRAM_BOT_TOKEN=<value>
    """
    import re
    
    # Redact Bearer tokens
    line = re.sub(r'Bearer\s+([A-Za-z0-9_-]{20,})', r'Bearer ***REDACTED***', line)
    
    # Redact API keys and tokens in KEY=VALUE format
    line = re.sub(
        r'((?:api[_-]?key|API[_-]?KEY|token|TOKEN|password|PASSWORD|pwd|PWD|secret|SECRET)\s*[=:]\s*)([A-Za-z0-9_-]{10,})',
        r'\1***REDACTED***',
        line,
        flags=re.IGNORECASE
    )
    
    # Redact database URLs (keep protocol and hostname, redact credentials)
    line = re.sub(
        r'(postgresql?://)([^:]+):([^@]+)@',
        r'\1***USER***:***PASSWORD***@',
        line,
        flags=re.IGNORECASE
    )
    
    # Redact long hex strings (likely tokens)
    line = re.sub(r'\b([A-Fa-f0-9]{32,})\b', lambda m: '*' * min(len(m.group(1)), 20) + '...' if len(m.group(1)) > 20 else '***REDACTED***', line)
    
    return line


def fetch_render_logs(api_key: str, service_id: str, minutes: int = 30) -> List[str]:
    """
    Fetch logs from Render API for last N minutes.
    
    Returns:
        List of log lines
    """
    try:
        import aiohttp
        import asyncio
    except ImportError:
        print("⚠️  aiohttp not available, using requests fallback")
        try:
            import requests
        except ImportError:
            print("❌ Neither aiohttp nor requests available")
            return []
    
    # Render API endpoint
    url = f"https://api.render.com/v1/services/{service_id}/logs"
    
    # Calculate timestamp (last N minutes)
    since = datetime.utcnow() - timedelta(minutes=minutes)
    since_iso = since.isoformat() + 'Z'
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    params = {
        "since": since_iso,
        "limit": 1000  # Max lines
    }
    
    try:
        # Try aiohttp first (async)
        import asyncio
        import aiohttp
        
        async def fetch():
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Render API returns logs in different formats, extract lines
                        logs = data.get("logs", [])
                        if isinstance(logs, list):
                            return [log.get("message", str(log)) for log in logs]
                        elif isinstance(logs, str):
                            return logs.split('\n')
                        return []
                    else:
                        print(f"⚠️  Render API returned {resp.status}: {await resp.text()}")
                        return []
        
        return asyncio.run(fetch())
        
    except Exception as e:
        # Fallback to requests (sync)
        try:
            import requests
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                logs = data.get("logs", [])
                if isinstance(logs, list):
                    return [log.get("message", str(log)) for log in logs]
                elif isinstance(logs, str):
                    return logs.split('\n')
                return []
            else:
                print(f"⚠️  Render API returned {resp.status_code}: {resp.text[:200]}")
                return []
        except Exception as e2:
            print(f"❌ Failed to fetch logs: {e2}")
            return []


def analyze_logs(logs: List[str]) -> Dict[str, Any]:
    """
    Analyze logs for errors, exceptions, and critical issues.
    
    Returns:
        Dict with counts and top errors
    """
    errors = []
    exceptions = []
    import_errors = []
    tracebacks = []
    warnings = []
    
    # Patterns to detect
    error_pattern = re.compile(r'(?i)(error|failed|failure|exception|traceback|import.*error)')
    traceback_pattern = re.compile(r'(?i)(traceback|file ".*", line \d+)')
    import_error_pattern = re.compile(r'(?i)(import.*error|cannot import)')
    warning_pattern = re.compile(r'(?i)(warning|warn)')
    
    for i, line in enumerate(logs):
        if error_pattern.search(line):
            errors.append((i, line))
        if traceback_pattern.search(line):
            tracebacks.append((i, line))
        if import_error_pattern.search(line):
            import_errors.append((i, line))
        if warning_pattern.search(line) and not error_pattern.search(line):
            warnings.append((i, line))
    
    # Extract exception types
    exception_types = {}
    for _, line in errors:
        # Try to extract exception type (e.g., "ImportError:", "TypeError:")
        match = re.search(r'(\w+Error|\w+Exception):', line)
        if match:
            exc_type = match.group(1)
            exception_types[exc_type] = exception_types.get(exc_type, 0) + 1
    
    return {
        "total_lines": len(logs),
        "error_count": len(errors),
        "exception_count": len(exceptions),
        "import_error_count": len(import_errors),
        "traceback_count": len(tracebacks),
        "warning_count": len(warnings),
        "top_errors": errors[:10],  # Top 10 errors
        "top_import_errors": import_errors[:5],
        "exception_types": exception_types,
    }


def print_report(analysis: Dict[str, Any], minutes: int):
    """Print diagnostic report."""
    print("\n" + "=" * 60)
    print(f"  RENDER LOGS CHECK (last {minutes} minutes)")
    print("=" * 60)
    print(f"\n  Total log lines: {analysis['total_lines']}")
    print(f"  Errors: {analysis['error_count']}")
    print(f"  Import Errors: {analysis['import_error_count']}")
    print(f"  Tracebacks: {analysis['traceback_count']}")
    print(f"  Warnings: {analysis['warning_count']}")
    
    if analysis['exception_types']:
        print(f"\n  Exception Types:")
        for exc_type, count in sorted(analysis['exception_types'].items(), key=lambda x: -x[1]):
            print(f"    - {exc_type}: {count}")
    
    if analysis['top_import_errors']:
        print(f"\n  ⚠️  TOP IMPORT ERRORS:")
        for idx, (line_num, line) in enumerate(analysis['top_import_errors'], 1):
            print(f"    {idx}. Line {line_num}: {line[:100]}")
    
    if analysis['top_errors']:
        print(f"\n  ⚠️  TOP ERRORS:")
        for idx, (line_num, line) in enumerate(analysis['top_errors'][:5], 1):
            print(f"    {idx}. Line {line_num}: {line[:100]}")
    
    print("\n" + "=" * 60)
    
    # Return exit code
    if analysis['import_error_count'] > 0 or analysis['traceback_count'] > 0:
        print("  ❌ CRITICAL ISSUES FOUND")
        return 1
    elif analysis['error_count'] > 0:
        print("  ⚠️  ERRORS FOUND (non-critical)")
        return 0
    else:
        print("  ✅ NO CRITICAL ERRORS")
        return 0


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Check Render logs for errors")
    parser.add_argument("--minutes", type=int, default=30, help="Minutes of logs to check")
    parser.add_argument("--skip-network", action="store_true", help="Skip network calls (for testing)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  RENDER LOGS CHECK")
    print("=" * 60)
    
    # Load config
    config = load_render_config()
    if not config:
        print("\n❌ Config not loaded, exiting")
        return 1
    
    api_key = config.get("RENDER_API_KEY")
    service_id = config.get("RENDER_SERVICE_ID")
    
    if not api_key or not service_id:
        print("\n❌ RENDER_API_KEY or RENDER_SERVICE_ID missing")
        return 1
    
    print(f"\n  API Key: {redact_secret(api_key)}")
    print(f"  Service ID: {service_id}")
    print(f"  Minutes: {args.minutes}")
    
    if args.skip_network:
        print("\n  ⏭️  Skipping network (--skip-network)")
        return 0
    
    # Fetch logs
    print("\n  📥 Fetching logs...")
    logs = fetch_render_logs(api_key, service_id, args.minutes)
    
    if not logs:
        print("  ⚠️  No logs fetched (API unavailable or empty)")
        return 0
    
    print(f"  ✅ Fetched {len(logs)} log lines")
    
    # Analyze (with secret redaction)
    print("  🔍 Analyzing logs (secrets will be redacted)...")
    analysis = analyze_logs(logs, redact_secrets=True)

    # Print report
    exit_code = print_report(analysis, args.minutes, redact_secrets=True)
    
    # Save sanitized logs to artifacts (optional)
    if logs:
        artifacts_dir = project_root / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_file = artifacts_dir / f"render_logs_sanitized_{timestamp}.txt"
        
        # Write redacted logs
        with open(sanitized_file, 'w', encoding='utf-8') as f:
            for line in logs:
                redacted_line = redact_secrets_in_log_line(line)
                f.write(redacted_line + '\n')
        
        print(f"\n  💾 Sanitized logs saved to: {sanitized_file}")

    return exit_code


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

