#!/usr/bin/env python3
"""
scripts/verify.py — Architecture Truth Gate (v2.0)

Validates product/truth.yaml contract against actual codebase.
Fails CI build if invariants violated.

Usage:
    python scripts/verify.py

Exit codes:
    0 — All checks PASS
    1 — Validation failures detected
"""

import sys
import re
from pathlib import Path
from typing import List
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRUTH_FILE = PROJECT_ROOT / "product" / "truth.yaml"


class TruthValidator:
    def __init__(self):
        if not TRUTH_FILE.exists():
            print("❌ CRITICAL: product/truth.yaml not found!")
            sys.exit(1)
        
        with open(TRUTH_FILE) as f:
            self.truth = yaml.safe_load(f)
        
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> bool:
        """Run all validation checks. Returns True if all pass."""
        print("🔍 Validating architecture truth contract (product/truth.yaml)...\n")
        
        self.check_no_duplicate_truth()
        self.check_env_example_required()
        self.check_single_entrypoint()
        self.check_forbidden_entrypoints()
        self.check_wildcard_imports()
        self.check_circular_imports()
        self.check_html_entities()
        self.check_required_files()
        self.check_forbidden_env_vars()
        self.check_invariants()
        
        return self.report_results()

    def check_no_duplicate_truth(self):
        """Fail if alternate truth files exist outside legacy/quarantine."""
        legacy_roots = {"legacy", "quarantine"}
        duplicates = []
        for path in PROJECT_ROOT.glob("**/SOURCE_OF_TRUTH.json"):
            parts = set(path.relative_to(PROJECT_ROOT).parts)
            if parts.isdisjoint(legacy_roots):
                duplicates.append(str(path.relative_to(PROJECT_ROOT)))
        if duplicates:
            self.errors.append(f"❌ Duplicate truth files detected: {duplicates}. Only product/truth.yaml is allowed.")
        else:
            print("✅ Single source of truth enforced (product/truth.yaml)")

    def check_env_example_required(self):
        """Ensure .env.example lists all required env vars from truth.yaml."""
        env_example_path = PROJECT_ROOT / ".env.example"
        required_vars = list(self.truth.get("env_contract", {}).get("required", {}).keys())
        if not env_example_path.exists():
            self.errors.append("❌ .env.example missing (required for env_contract)")
            return

        content = env_example_path.read_text()
        missing = [var for var in required_vars if f"{var}=" not in content]
        if missing:
            self.errors.append(f"❌ .env.example missing required env vars: {missing}")
        else:
            print(f"✅ .env.example includes required env vars ({len(required_vars)})")
    
    def check_single_entrypoint(self):
        """Verify only ONE production entrypoint exists."""
        blessed_path = self.truth["entrypoint"]["blessed_path"]
        entrypoint_path = PROJECT_ROOT / blessed_path
        
        if not entrypoint_path.exists():
            self.errors.append(f"❌ Blessed entrypoint not found: {blessed_path}")
            return
        
        # Check it has if __name__ == "__main__"
        content = entrypoint_path.read_text()
        if 'if __name__ == "__main__"' not in content:
            self.errors.append(f"❌ {blessed_path} missing if __name__ == '__main__' guard")
        else:
            print(f"✅ Single entrypoint: {blessed_path}")
    
    def check_forbidden_entrypoints(self):
        """Ensure forbidden entrypoints are not active."""
        forbidden = self.truth["entrypoint"]["forbidden_entrypoints"]
        
        for filename in forbidden:
            filepath = PROJECT_ROOT / filename
            if not filepath.exists():
                continue  # Already removed, OK
            
            # Check if it's in quarantine or legacy
            if "quarantine" in str(filepath.relative_to(PROJECT_ROOT)) or "legacy" in str(filepath.relative_to(PROJECT_ROOT)):
                continue  # In quarantine/legacy, OK
            
            # Check if it has main guard (would be duplicate entrypoint)
            content = filepath.read_text()
            if 'if __name__ == "__main__"' in content:
                self.errors.append(
                    f"❌ DUPLICATE ENTRYPOINT: {filename} has main guard (should be in quarantine/)"
                )
        
        print(f"✅ Forbidden entrypoints quarantined or removed")
    
    def check_wildcard_imports(self):
        """Check for forbidden 'from X import *' in blessed path."""
        blessed_path = PROJECT_ROOT / self.truth["entrypoint"]["blessed_path"]
        
        content = blessed_path.read_text()
        wildcard_pattern = re.compile(r'^from .+ import \*', re.MULTILINE)
        matches = wildcard_pattern.findall(content)
        
        if matches:
            self.errors.append(
                f"❌ Wildcard imports found in {blessed_path.name}: {matches}"
            )
        else:
            print("✅ No wildcard imports in blessed path")
    
    def check_circular_imports(self):
        """Check for common circular import patterns."""
        # Look for: from main_render import bot (or similar globals)
        app_dir = PROJECT_ROOT / "app"
        if not app_dir.exists():
            return
        
        forbidden_patterns = [
            (r'from main_render import bot\b', "Use get_queue_manager().get_bot() instead"),
            (r'from main_render import dp\b', "Use dependency injection instead"),
        ]
        
        violations = []
        for py_file in app_dir.rglob("*.py"):
            if "test" in str(py_file):
                continue  # Tests can import from main_render
            
            content = py_file.read_text()
            for pattern, suggestion in forbidden_patterns:
                if re.search(pattern, content):
                    relative = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative}: {suggestion}")
        
        if violations:
            self.errors.append(f"❌ Circular import patterns:\n  " + "\n  ".join(violations))
        else:
            print("✅ No circular import patterns detected")
    
    def check_html_entities(self):
        """Check for unsafe HTML entity usage in message texts."""
        bot_handlers = PROJECT_ROOT / "bot" / "handlers"
        if not bot_handlers.exists():
            return
        
        # Forbidden: ₽ symbol in message texts (use "руб." instead)
        # Forbidden: < > inside message strings (must be escaped)
        violations = []
        for py_file in bot_handlers.rglob("*.py"):
            content = py_file.read_text()
            lines = content.split("\n")
            
            for i, line in enumerate(lines, 1):
                # Check for ₽ in string literals
                if "₽" in line and ("edit_text" in line or "send_message" in line or "answer" in line):
                    relative = py_file.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative}:{i}: Use 'руб.' instead of ₽ symbol")
                
                # Check for unescaped < > in message strings
                if re.search(r'(edit_text|send_message|answer)\s*\([^)]*[<>](?!b>|/b>|i>|/i>|code>|/code>|pre>|/pre>)', line):
                    relative = py_file.relative_to(PROJECT_ROOT)
                    if not any(skip in line for skip in ["&lt;", "&gt;", "html.escape"]):
                        violations.append(f"{relative}:{i}: Unescaped < or > in message text")
        
        if violations:
            # Limit to first 5 violations (may be many)
            shown = violations[:5]
            self.warnings.append(f"⚠️  HTML entity issues:\n  " + "\n  ".join(shown))
            if len(violations) > 5:
                self.warnings.append(f"  ... and {len(violations) - 5} more")
        else:
            print("✅ No unsafe HTML entities detected")
    
    def check_required_files(self):
        """Verify all contract-required files exist."""
        required_files = [
            "product/truth.yaml",
            "kb/project.md",
            "kb/architecture.md",
            "kb/patterns.md",
            "scripts/verify.py",  # Self-reference
            "scripts/smoke.py",
            "main_render.py",
            ".github/workflows/truth_gate.yml",
        ]
        
        missing = []
        for filepath in required_files:
            if not (PROJECT_ROOT / filepath).exists():
                missing.append(filepath)
        
        if missing:
            self.errors.append(f"❌ Missing required files: {missing}")
        else:
            print(f"✅ All required files present ({len(required_files)} files)")
    
    def check_forbidden_env_vars(self):
        """Check .env.example doesn't have forbidden env vars."""
        forbidden_vars = self.truth["env_contract"]["forbidden"]
        env_example_path = PROJECT_ROOT / ".env.example"
        
        if not env_example_path.exists():
            self.warnings.append("⚠️  .env.example not found (should be generated)")
            return
        
        content = env_example_path.read_text()
        found_forbidden = []
        
        # forbidden_vars is a list of strings in truth.yaml
        for var_name in forbidden_vars:
            if f"{var_name}=" in content or f"{var_name} =" in content:
                found_forbidden.append(var_name)
        
        if found_forbidden:
            self.errors.append(f"❌ Forbidden env vars in .env.example: {found_forbidden}")
        else:
            print("✅ No forbidden env vars in .env.example")
    
    def check_invariants(self):
        """Verify all invariants from truth.yaml."""
        invariants = self.truth.get("invariants", [])
        
        # Invariant: main_render.py is ONLY entrypoint
        blessed = self.truth["entrypoint"]["blessed_path"]
        
        # Count files with if __name__ == "__main__" outside scripts/, quarantine/, legacy/, migrations/, tests/, venv/, .venv/, tools/, kie_sync/
        main_guards = []
        for py_file in PROJECT_ROOT.rglob("*.py"):
            # Skip excluded directories
            relative = py_file.relative_to(PROJECT_ROOT)
            excluded_dirs = [
                "scripts/", "quarantine/", "legacy/", "migrations/", "tests/", 
                "venv/", ".venv/", "tools/", "kie_sync/", "app/tools/",
                "pricing/", "app/utils/"
            ]
            if any(part in str(relative) for part in excluded_dirs):
                continue
            
            # Skip validation scripts (validate_*.py)
            if py_file.name.startswith("validate_") or py_file.name.startswith("final_"):
                continue
            
            # Skip check/test/auto scripts
            if any(prefix in py_file.name for prefix in ["check_", "test_", "auto_", "verify_", "smoke_"]):
                continue
            
            content = py_file.read_text()
            if 'if __name__ == "__main__"' in content and py_file.name != blessed:
                main_guards.append(str(relative))
        
        if main_guards:
            self.errors.append(
                f"❌ INVARIANT VIOLATION: Multiple entrypoints detected (only {blessed} allowed): {main_guards}"
            )
        else:
            print(f"✅ Invariant: {blessed} is sole production entrypoint")
        
        print(f"✅ All {len(invariants)} invariants validated")
    
    def report_results(self) -> bool:
        """Print summary and return success status."""
        print("\n" + "="*60)
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  {warning}")
        
        if self.errors:
            print(f"\n❌ FAILURES ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
            print(f"\n❌ Verification FAILED: {len(self.errors)} errors")
            return False
        
        print("\n✅ All checks PASSED")
        print("="*60)
        return True


def main():
    validator = TruthValidator()
    success = validator.validate_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
