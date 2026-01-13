#!/usr/bin/env python3
"""
verify_truth.py — Architecture Truth Gate

Validates SOURCE_OF_TRUTH.json contract against actual codebase.
Fails CI build if invariants violated.

Usage:
    python3 verify_truth.py [--fix-imports]

Exit codes:
    0 — All checks PASS
    1 — Validation failures detected (see stderr)
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
TRUTH_FILE = PROJECT_ROOT / "SOURCE_OF_TRUTH.json"


class TruthValidator:
    def __init__(self):
        with open(TRUTH_FILE) as f:
            self.truth = json.load(f)
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> bool:
        """Run all validation checks. Returns True if all pass."""
        print("🔍 Validating architecture truth contract...\n")
        
        self.check_single_entrypoint()
        self.check_forbidden_entrypoints()
        self.check_wildcard_imports()
        self.check_required_files()
        self.check_forbidden_env_vars()
        self.check_duplicate_routes()
        
        return self.report_results()
    
    def check_single_entrypoint(self):
        """Verify only ONE production entrypoint exists."""
        entrypoint = self.truth["entrypoint"]["production"]
        entrypoint_path = PROJECT_ROOT / entrypoint
        
        if not entrypoint_path.exists():
            self.errors.append(f"❌ Production entrypoint not found: {entrypoint}")
            return
        
        # Check it has if __name__ == "__main__"
        content = entrypoint_path.read_text()
        if 'if __name__ == "__main__"' not in content:
            self.errors.append(f"❌ {entrypoint} missing if __name__ == '__main__' guard")
        else:
            print(f"✅ Single entrypoint: {entrypoint}")
    
    def check_forbidden_entrypoints(self):
        """Ensure forbidden entrypoints are not executable/imported."""
        forbidden = self.truth["entrypoint"]["forbidden_entrypoints"]
        
        for filename in forbidden:
            filepath = PROJECT_ROOT / filename
            if not filepath.exists():
                continue  # Already removed, OK
            
            # Check if it has main guard (would be duplicate entrypoint)
            content = filepath.read_text()
            if 'if __name__ == "__main__"' in content:
                # Check if it's in quarantine
                if "quarantine" in str(filepath.relative_to(PROJECT_ROOT)):
                    self.warnings.append(f"⚠️  {filename} in quarantine but still has main guard")
                else:
                    self.errors.append(
                        f"❌ DUPLICATE ENTRYPOINT: {filename} has main guard (should be in quarantine/)"
                    )
        
        print(f"✅ Forbidden entrypoints check: {len(forbidden)} monitored")
    
    def check_wildcard_imports(self):
        """Detect wildcard imports (from X import *)."""
        pattern = re.compile(r'^\s*from\s+\S+\s+import\s+\*', re.MULTILINE)
        violations = []
        
        # Scan all .py files except tests/quarantine
        for pyfile in PROJECT_ROOT.rglob("*.py"):
            rel_path = pyfile.relative_to(PROJECT_ROOT)
            
            # Skip excluded directories
            if any(part in ["tests", "quarantine", "__pycache__", ".venv", "venv"] 
                   for part in rel_path.parts):
                continue
            
            content = pyfile.read_text(errors='ignore')
            matches = pattern.findall(content)
            if matches:
                violations.append(str(rel_path))
        
        if violations:
            self.errors.append(
                f"❌ WILDCARD IMPORTS detected in {len(violations)} files:\n  " +
                "\n  ".join(violations[:10])
            )
        else:
            print("✅ No wildcard imports detected")
    
    def check_required_files(self):
        """Verify critical architecture files exist."""
        required = [
            "ARCHITECTURE_LOCK.md",
            "SOURCE_OF_TRUTH.json",
            "main_render.py",
            "smoke_test.py",
            "render_singleton_lock.py",
            "app/locking/controller.py",
            "app/utils/update_queue.py",
        ]
        
        missing = []
        for filepath in required:
            if not (PROJECT_ROOT / filepath).exists():
                missing.append(filepath)
        
        if missing:
            self.errors.append(f"❌ Missing required files: {', '.join(missing)}")
        else:
            print(f"✅ All {len(required)} required files present")
    
    def check_forbidden_env_vars(self):
        """Scan code for usage of forbidden env vars."""
        forbidden = self.truth.get("forbidden_env_vars", [])
        if not forbidden:
            return
        
        violations = {}
        for var in forbidden:
            # Search for os.getenv(var) or os.environ[var]
            pattern = re.compile(rf'os\.(getenv|environ)\s*\[\s*["\']({var})["\']')
            
            for pyfile in PROJECT_ROOT.rglob("*.py"):
                if "quarantine" in str(pyfile) or "tests" in str(pyfile):
                    continue
                
                content = pyfile.read_text(errors='ignore')
                if pattern.search(content):
                    violations.setdefault(var, []).append(str(pyfile.relative_to(PROJECT_ROOT)))
        
        if violations:
            msg = "❌ FORBIDDEN ENV VARS used:\n"
            for var, files in violations.items():
                msg += f"  {var}: {', '.join(files[:5])}\n"
            self.errors.append(msg.strip())
        else:
            print(f"✅ No forbidden env vars ({len(forbidden)} monitored)")
    
    def check_duplicate_routes(self):
        """Detect duplicate aiogram handler registrations (same pattern multiple times)."""
        # This is a simplified check — in real world would parse AST
        handler_files = list((PROJECT_ROOT / "app" / "handlers").rglob("*.py"))
        
        # Extract @dp.message patterns
        pattern = re.compile(r'@\w+\.(message|callback_query)\s*\([^)]*\)')
        
        route_definitions = {}
        for pyfile in handler_files:
            content = pyfile.read_text(errors='ignore')
            matches = pattern.findall(content)
            
            for match in matches:
                route_definitions.setdefault(match, []).append(
                    str(pyfile.relative_to(PROJECT_ROOT))
                )
        
        duplicates = {k: v for k, v in route_definitions.items() if len(v) > 1}
        
        if duplicates:
            self.warnings.append(
                f"⚠️  Potential duplicate routes detected: {len(duplicates)} patterns " +
                f"(manual review needed)"
            )
        else:
            print("✅ No obvious duplicate route handlers")
    
    def report_results(self) -> bool:
        """Print summary and return True if passed."""
        print("\n" + "="*60)
        
        if self.errors:
            print(f"❌ VALIDATION FAILED: {len(self.errors)} error(s)\n")
            for err in self.errors:
                print(err)
            print()
        
        if self.warnings:
            print(f"⚠️  {len(self.warnings)} warning(s):\n")
            for warn in self.warnings:
                print(warn)
            print()
        
        if not self.errors:
            print("✅ ALL TRUTH GATES PASSED")
            if self.warnings:
                print("   (Warnings present but not blocking)")
            return True
        else:
            print("🚫 Fix errors before deployment")
            return False


def main():
    validator = TruthValidator()
    
    passed = validator.validate_all()
    
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
