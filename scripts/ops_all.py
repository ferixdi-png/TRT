#!/usr/bin/env python3
"""
Ops All - Comprehensive operational check: Render logs + DB check + Critical 5 analysis.

Runs all operational checks and generates a unified report.
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import existing scripts (using importlib to avoid circular imports)
import importlib.util

def import_module_from_file(file_path: Path, module_name: str):
    """Import module from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Import render_logs_check module
render_logs_module = import_module_from_file(
    project_root / "scripts" / "render_logs_check.py",
    "render_logs_check"
)
load_render_config = render_logs_module.load_render_config
fetch_render_logs = render_logs_module.fetch_render_logs
analyze_logs = render_logs_module.analyze_logs
redact_secrets_in_log_line = render_logs_module.redact_secrets_in_log_line

# Import db_readonly_check module
db_check_module = import_module_from_file(
    project_root / "scripts" / "db_readonly_check.py",
    "db_readonly_check"
)
load_db_config = db_check_module.load_db_config
check_database_connection = db_check_module.check_database_connection
get_connection_stats = db_check_module.get_connection_stats
get_table_list = db_check_module.get_table_list
check_recent_errors = db_check_module.check_recent_errors
check_migrations_table = db_check_module.check_migrations_table


def run_render_logs_check(minutes: int = 30) -> Dict[str, Any]:
    """
    Run Render logs check and return results.
    
    Returns:
        Dict with logs analysis results
    """
    print("\n" + "=" * 70)
    print("  STEP 1: RENDER LOGS CHECK")
    print("=" * 70)
    
    config = load_render_config()
    if not config:
        return {
            "status": "error",
            "error": "Config not loaded",
            "logs": [],
            "analysis": {}
        }
    
    api_key = config.get("RENDER_API_KEY")
    service_id = config.get("RENDER_SERVICE_ID")
    
    if not api_key or not service_id:
        return {
            "status": "error",
            "error": "RENDER_API_KEY or RENDER_SERVICE_ID missing",
            "logs": [],
            "analysis": {}
        }
    
    print(f"  📥 Fetching logs (last {minutes} minutes)...")
    logs = fetch_render_logs(api_key, service_id, minutes)
    
    if not logs:
        return {
            "status": "warning",
            "error": "No logs fetched",
            "logs": [],
            "analysis": {}
        }
    
    print(f"  ✅ Fetched {len(logs)} log lines")
    
    print("  🔍 Analyzing logs...")
    analysis = analyze_logs(logs, redact_secrets=True)
    
    return {
        "status": "ok",
        "logs_count": len(logs),
        "logs": logs[:100],  # Keep first 100 lines for report
        "analysis": analysis,
        "timestamp": datetime.now().isoformat()
    }


async def run_db_check() -> Dict[str, Any]:
    """
    Run DB readonly check and return results.
    
    Returns:
        Dict with DB check results
    """
    print("\n" + "=" * 70)
    print("  STEP 2: DATABASE CHECK")
    print("=" * 70)
    
    config = load_db_config()
    if not config:
        return {
            "status": "error",
            "error": "Config not loaded"
        }
    
    db_url = config.get("DATABASE_URL_READONLY")
    if not db_url:
        return {
            "status": "error",
            "error": "DATABASE_URL_READONLY missing"
        }
    
    print("  📥 Checking DB connectivity...")
    conn_result = await check_database_connection(db_url)
    
    if conn_result["status"] != "ok":
        return {
            "status": "error",
            "connection": conn_result,
            "error": conn_result.get("error", "Connection failed")
        }
    
    print("  ✅ Connection OK")
    
    # Get connection stats
    print("  📊 Getting connection statistics...")
    stats = await get_connection_stats(db_url)
    
    # Get table list
    print("  📋 Getting table list...")
    tables = await get_table_list(db_url)
    
    # Get recent errors
    print("  🔍 Checking recent errors...")
    errors = await check_recent_errors(db_url, hours=24)
    
    # Check migrations
    print("  🔍 Checking migrations...")
    migrations_ok = await check_migrations_table(db_url)
    
    return {
        "status": "ok",
        "connection": conn_result,
        "stats": stats,
        "tables": tables[:20],  # First 20 tables
        "tables_count": len(tables),
        "recent_errors": errors[:10],  # Top 10 errors
        "recent_errors_count": len(errors),
        "migrations_ok": migrations_ok,
        "timestamp": datetime.now().isoformat()
    }


def analyze_critical5(render_results: Dict[str, Any], db_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Analyze and rank top 5 critical issues.
    
    Returns:
        List of top 5 critical issues with evidence and recommendations
    """
    critical_issues = []
    
    # 1. Render logs: ImportError / Traceback (CRITICAL)
    render_analysis = render_results.get("analysis", {})
    if render_analysis.get("import_error_count", 0) > 0:
        critical_issues.append({
            "severity": "CRITICAL",
            "category": "Startup",
            "issue": "ImportError detected in Render logs",
            "count": render_analysis["import_error_count"],
            "evidence": render_analysis.get("top_import_errors", [])[:3],
            "recommendation": "Fix import errors immediately - app may not start correctly",
            "impact": "Breaks app startup"
        })
    
    if render_analysis.get("traceback_count", 0) > 0:
        critical_issues.append({
            "severity": "CRITICAL",
            "category": "Runtime",
            "issue": "Traceback detected in Render logs",
            "count": render_analysis["traceback_count"],
            "evidence": render_analysis.get("top_errors", [])[:2],
            "recommendation": "Investigate tracebacks - app may be crashing",
            "impact": "Breaks app runtime"
        })
    
    # 2. DB: Connection failures (CRITICAL)
    if db_results.get("status") == "error":
        critical_issues.append({
            "severity": "CRITICAL",
            "category": "Database",
            "issue": "Database connection failed",
            "count": 1,
            "evidence": [{"error": db_results.get("error", "Unknown error")}],
            "recommendation": "Check DATABASE_URL_READONLY and database availability",
            "impact": "Breaks all DB operations"
        })
    
    # 3. DB: High connection usage (WARNING)
    db_stats = db_results.get("stats", {})
    if db_stats.get("active_connections") and db_stats.get("max_connections"):
        usage_pct = (db_stats["active_connections"] / db_stats["max_connections"]) * 100
        if usage_pct > 80:
            critical_issues.append({
                "severity": "WARNING",
                "category": "Database",
                "issue": f"High database connection usage: {usage_pct:.1f}%",
                "count": db_stats["active_connections"],
                "evidence": [{
                    "active": db_stats["active_connections"],
                    "max": db_stats["max_connections"],
                    "usage_pct": usage_pct
                }],
                "recommendation": "Monitor connection pool - may need to increase max_connections or optimize",
                "impact": "May cause connection timeouts"
            })
    
    # 4. DB: Recent errors (WARNING/INFO)
    db_errors = db_results.get("recent_errors", [])
    if db_errors and len(db_errors) > 0:
        error_count = db_results.get("recent_errors_count", 0)
        critical_issues.append({
            "severity": "WARNING" if error_count > 5 else "INFO",
            "category": "Application",
            "issue": f"Recent errors in app_events: {error_count} in last 24h",
            "count": error_count,
            "evidence": db_errors[:3],
            "recommendation": "Review error patterns and fix root causes",
            "impact": "Degrades user experience"
        })
    
    # 5. Render logs: High error rate (WARNING)
    render_error_count = render_analysis.get("error_count", 0)
    render_total_lines = render_analysis.get("total_lines", 1)
    error_rate = (render_error_count / render_total_lines) * 100 if render_total_lines > 0 else 0
    
    if error_rate > 10:  # More than 10% error rate
        critical_issues.append({
            "severity": "WARNING",
            "category": "Application",
            "issue": f"High error rate in logs: {error_rate:.1f}% ({render_error_count} errors)",
            "count": render_error_count,
            "evidence": render_analysis.get("top_errors", [])[:3],
            "recommendation": "Investigate error patterns and fix common issues",
            "impact": "Degrades reliability"
        })
    
    # 6. Render logs: Exception types (INFO/WARNING)
    exception_types = render_analysis.get("exception_types", {})
    if exception_types:
        top_exception = max(exception_types.items(), key=lambda x: x[1])
        if top_exception[1] > 3:  # More than 3 occurrences
            critical_issues.append({
                "severity": "WARNING" if top_exception[1] > 10 else "INFO",
                "category": "Application",
                "issue": f"Frequent exception: {top_exception[0]} ({top_exception[1]} times)",
                "count": top_exception[1],
                "evidence": [{"exception_type": top_exception[0], "count": top_exception[1]}],
                "recommendation": f"Fix root cause of {top_exception[0]} exceptions",
                "impact": "Causes instability"
            })
    
    # Sort by severity (CRITICAL > WARNING > INFO) and count
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    critical_issues.sort(key=lambda x: (severity_order.get(x["severity"], 99), -x["count"]))
    
    # Return top 5
    return critical_issues[:5]


def generate_report(render_results: Dict[str, Any], db_results: Dict[str, Any], critical5: List[Dict[str, Any]]) -> str:
    """
    Generate markdown report.
    
    Returns:
        Markdown report string
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report = f"""# Ops Report - {timestamp}

## Summary

- **Render Logs**: {render_results.get('status', 'unknown')}
- **Database Check**: {db_results.get('status', 'unknown')}
- **Critical Issues**: {len(critical5)}

---

## Critical 5 Issues

"""
    
    if not critical5:
        report += "✅ **No critical issues found**\n\n"
    else:
        for idx, issue in enumerate(critical5, 1):
            report += f"""### {idx}. [{issue['severity']}] {issue['issue']}

- **Category**: {issue['category']}
- **Count**: {issue['count']}
- **Impact**: {issue['impact']}
- **Recommendation**: {issue['recommendation']}

**Evidence**:
```json
{json.dumps(issue['evidence'], indent=2)}
```

---

"""
    
    report += f"""
## Render Logs Analysis

- **Total lines**: {render_results.get('analysis', {}).get('total_lines', 0)}
- **Errors**: {render_results.get('analysis', {}).get('error_count', 0)}
- **Import Errors**: {render_results.get('analysis', {}).get('import_error_count', 0)}
- **Tracebacks**: {render_results.get('analysis', {}).get('traceback_count', 0)}
- **Warnings**: {render_results.get('analysis', {}).get('warning_count', 0)}

"""
    
    report += f"""
## Database Check

- **Connection**: {db_results.get('connection', {}).get('status', 'unknown')}
- **Latency**: {db_results.get('connection', {}).get('latency_ms', 'N/A')}ms
- **Active Connections**: {db_results.get('stats', {}).get('active_connections', 'N/A')}
- **Max Connections**: {db_results.get('stats', {}).get('max_connections', 'N/A')}
- **Tables**: {db_results.get('tables_count', 0)}
- **Recent Errors (24h)**: {db_results.get('recent_errors_count', 0)}
- **Migrations OK**: {db_results.get('migrations_ok', False)}

---

*Generated at {timestamp}*
"""
    
    return report


def save_artifacts(render_results: Dict[str, Any], db_results: Dict[str, Any], critical5: List[Dict[str, Any]], report: str):
    """Save all artifacts to artifacts/ directory."""
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save JSON data
    json_data = {
        "timestamp": datetime.now().isoformat(),
        "render_logs": render_results,
        "db_check": db_results,
        "critical5": critical5
    }
    
    json_file = artifacts_dir / f"ops_report_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, default=str)
    
    # Save markdown report
    md_file = artifacts_dir / f"ops_report_{timestamp}.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Save latest symlink (or copy on Windows)
    latest_json = artifacts_dir / "ops_report_latest.json"
    latest_md = artifacts_dir / "ops_report_latest.md"
    
    try:
        if latest_json.exists():
            latest_json.unlink()
        if latest_md.exists():
            latest_md.unlink()
    except Exception:
        pass
    
    try:
        import shutil
        shutil.copy(json_file, latest_json)
        shutil.copy(md_file, latest_md)
    except Exception as e:
        print(f"  ⚠️  Could not create latest symlinks: {e}")
    
    return json_file, md_file


async def main_async():
    """Main async function."""
    print("=" * 70)
    print("  OPS ALL - COMPREHENSIVE OPERATIONAL CHECK")
    print("=" * 70)
    
    # Step 1: Render logs check
    render_results = run_render_logs_check(minutes=30)
    
    # Step 2: DB check
    db_results = await run_db_check()
    
    # Step 3: Critical 5 analysis
    print("\n" + "=" * 70)
    print("  STEP 3: CRITICAL 5 ANALYSIS")
    print("=" * 70)
    
    critical5 = analyze_critical5(render_results, db_results)
    
    print(f"\n  🔍 Found {len(critical5)} critical issues:")
    for idx, issue in enumerate(critical5, 1):
        print(f"     {idx}. [{issue['severity']}] {issue['issue']} (count: {issue['count']})")
    
    # Step 4: Generate report
    print("\n" + "=" * 70)
    print("  STEP 4: GENERATING REPORT")
    print("=" * 70)
    
    report = generate_report(render_results, db_results, critical5)
    
    # Step 5: Save artifacts
    print("\n  💾 Saving artifacts...")
    json_file, md_file = save_artifacts(render_results, db_results, critical5, report)
    
    print(f"     ✅ JSON: {json_file}")
    print(f"     ✅ Markdown: {md_file}")
    print(f"     ✅ Latest: artifacts/ops_report_latest.json / .md")
    
    # Print summary
    print("\n" + "=" * 70)
    print("  ✅ OPS ALL COMPLETE")
    print("=" * 70)
    
    print(f"\n  Summary:")
    print(f"     Render Logs: {render_results.get('status', 'unknown')}")
    print(f"     DB Check: {db_results.get('status', 'unknown')}")
    print(f"     Critical Issues: {len(critical5)}")
    
    if critical5:
        print(f"\n  ⚠️  Top Critical Issue: [{critical5[0]['severity']}] {critical5[0]['issue']}")
    
    return 0


def main():
    """Main entry point."""
    try:
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

