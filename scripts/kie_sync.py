#!/usr/bin/env python3
"""
KIE Source-of-Truth Verifier and Sync Tool

Modes:
  - CHECK (default): Compare upstream docs with local registry, output report. NO writes.
  - UPDATE (--write): Apply safe changes to unlocked models only.

Hard Requirements:
  - Never changes locked models (locked=true or override=true)
  - Never adds new models without --add-model flag
  - Deterministic fingerprints for verification
  - Cached snapshots for CI (fixtures/kie_docs/)
  - Safe fields only: description, enums, defaults, constraints, pricing, docs_url
  - Unsafe fields (never auto-change): model_id, output_media_type, required fields, field types
"""

import sys
import json
import hashlib
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("⚠️  beautifulsoup4 not installed. Install with: pip install beautifulsoup4 lxml")

logger = logging.getLogger(__name__)


@dataclass
class ModelFingerprint:
    """Deterministic fingerprint for a model schema."""
    model_id: str
    category: str
    endpoint: str
    required_fields: Set[str]
    optional_fields: Set[str]
    field_types: Dict[str, str]
    enums: Dict[str, List[str]]
    defaults: Dict[str, Any]
    constraints: Dict[str, Dict[str, Any]]
    pricing_credits: Optional[float] = None
    pricing_rules: Optional[Dict[str, Any]] = None
    fingerprint_hash: str = ""
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of fingerprint."""
        # Normalize for deterministic hashing
        data = {
            "model_id": self.model_id,
            "category": self.category,
            "endpoint": self.endpoint,
            "required": sorted(self.required_fields),
            "optional": sorted(self.optional_fields),
            "types": {k: str(v) for k, v in sorted(self.field_types.items())},
            "enums": {k: sorted(v) for k, v in sorted(self.enums.items())},
            "defaults": {k: str(v) for k, v in sorted(self.defaults.items())},
            "constraints": json.dumps(self.constraints, sort_keys=True),
            "pricing_credits": self.pricing_credits,
            "pricing_rules": json.dumps(self.pricing_rules, sort_keys=True) if self.pricing_rules else None,
        }
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()[:16]


@dataclass
class ModelDiff:
    """Difference between local and upstream model."""
    model_id: str
    status: str  # "exact_match", "diff", "locked_diff", "parse_failure", "missing_upstream", "new_model"
    local_fingerprint: Optional[ModelFingerprint] = None
    upstream_fingerprint: Optional[ModelFingerprint] = None
    diffs: Dict[str, Any] = None  # Detailed differences
    confidence: str = "high"  # "high", "medium", "low", "needs_manual"
    notes: List[str] = None


class KIERegistrySync:
    """KIE Registry Sync Tool - CHECK and UPDATE modes."""
    
    def __init__(self, local_sot_path: str = "models/KIE_SOURCE_OF_TRUTH.json"):
        self.local_sot_path = Path(local_sot_path)
        self.cache_dir = Path("fixtures/kie_docs")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.report_path = Path("KIE_SYNC_REPORT.md")
        
        self.local_sot: Dict[str, Any] = {}
        self.upstream_data: Dict[str, Any] = {}
        self.diffs: List[ModelDiff] = []
        
    def load_local_registry(self) -> Dict[str, Any]:
        """Load local source of truth."""
        if not self.local_sot_path.exists():
            logger.error(f"Local SOT not found: {self.local_sot_path}")
            return {}
        
        with open(self.local_sot_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.local_sot = data
        logger.info(f"✅ Loaded local registry: {len(data.get('models', {}))} models")
        return data
    
    def is_model_locked(self, model_id: str, model_data: Dict[str, Any]) -> bool:
        """Check if model is locked (should not be auto-updated)."""
        # Check for lock flags
        if model_data.get("locked", False) or model_data.get("override", False):
            return True
        
        # Check metadata
        metadata = model_data.get("_metadata", {})
        if metadata.get("locked", False) or metadata.get("override", False):
            return True
        
        return False
    
    def compute_fingerprint(self, model_id: str, model_data: Dict[str, Any], source: str = "local") -> ModelFingerprint:
        """Compute deterministic fingerprint for a model."""
        input_schema = model_data.get("input_schema", {})
        input_props = input_schema.get("input", {})
        
        # Extract properties (handle both "properties" and "examples" formats)
        properties = {}
        if isinstance(input_props, dict):
            if "properties" in input_props:
                properties = input_props["properties"]
            elif "type" in input_props and input_props.get("type") == "dict":
                # Try to infer from examples
                examples = input_props.get("examples", [])
                if examples and isinstance(examples[0], dict):
                    # Infer properties from first example
                    for key in examples[0].keys():
                        properties[key] = {"type": "unknown"}
        
        # Extract required fields
        required_fields = set()
        if "required" in input_props:
            required_fields = set(input_props["required"])
        elif "properties" in input_props:
            # Infer from properties
            for field_name, field_spec in input_props.get("properties", {}).items():
                if field_spec.get("required", False):
                    required_fields.add(field_name)
        
        # Extract optional fields
        optional_fields = set()
        field_types = {}
        enums = {}
        defaults = {}
        constraints = {}
        
        for field_name, field_spec in properties.items():
            if field_name not in required_fields:
                optional_fields.add(field_name)
            
            field_types[field_name] = field_spec.get("type", "unknown")
            
            if "enum" in field_spec or "options" in field_spec:
                enums[field_name] = field_spec.get("enum") or field_spec.get("options", [])
            
            if "default" in field_spec:
                defaults[field_name] = field_spec["default"]
            
            # Constraints
            field_constraints = {}
            if "max_length" in field_spec:
                field_constraints["max_length"] = field_spec["max_length"]
            if "min_value" in field_spec:
                field_constraints["min_value"] = field_spec["min_value"]
            if "max_value" in field_spec:
                field_constraints["max_value"] = field_spec["max_value"]
            if field_constraints:
                constraints[field_name] = field_constraints
        
        # Pricing
        pricing = model_data.get("pricing", {})
        pricing_credits = pricing.get("credits_per_gen")
        pricing_rules = pricing.get("pricing_rules")
        
        fingerprint = ModelFingerprint(
            model_id=model_id,
            category=model_data.get("category", "unknown"),
            endpoint=model_data.get("endpoint", "/api/v1/jobs/createTask"),
            required_fields=required_fields,
            optional_fields=optional_fields,
            field_types=field_types,
            enums=enums,
            defaults=defaults,
            constraints=constraints,
            pricing_credits=pricing_credits,
            pricing_rules=pricing_rules,
        )
        fingerprint.fingerprint_hash = fingerprint.compute_hash()
        return fingerprint
    
    def parse_upstream_docs(self, model_id: str, source_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Parse upstream docs page for a model.
        
        Returns parsed model data or None if parsing fails.
        Uses cached snapshot if available.
        """
        # Try cache first
        cache_file = self.cache_dir / f"{model_id.replace('/', '_')}.html"
        if cache_file.exists():
            logger.debug(f"Using cached snapshot: {cache_file}")
            html_content = cache_file.read_text(encoding='utf-8')
        else:
            # In CHECK mode, we don't fetch from network
            # User must refresh cache manually
            logger.warning(f"No cached snapshot for {model_id}. Run with --refresh-cache to fetch.")
            return None
        
        if not HAS_BS4:
            logger.error("BeautifulSoup4 not available. Cannot parse HTML.")
            return None
        
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            # TODO: Implement actual parsing logic
            # For now, return None to indicate parsing not implemented
            logger.warning(f"Parsing not fully implemented for {model_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse {model_id}: {e}")
            return None
    
    def check_all_models(self) -> List[ModelDiff]:
        """Run CHECK mode: compare all models and generate diffs."""
        logger.info("=" * 80)
        logger.info("KIE SYNC: CHECK MODE")
        logger.info("=" * 80)
        
        self.load_local_registry()
        models = self.local_sot.get("models", {})
        
        diffs = []
        exact_matches = 0
        locked_diffs = 0
        parse_failures = 0
        
        for model_id, model_data in models.items():
            is_locked = self.is_model_locked(model_id, model_data)
            local_fp = self.compute_fingerprint(model_id, model_data, "local")
            
            # Try to parse upstream
            source_url = model_data.get("source_url")
            upstream_data = self.parse_upstream_docs(model_id, source_url)
            
            if upstream_data is None:
                # No upstream data available (cached or parse failure)
                diff = ModelDiff(
                    model_id=model_id,
                    status="parse_failure" if source_url else "missing_upstream",
                    local_fingerprint=local_fp,
                    upstream_fingerprint=None,
                    diffs={},
                    confidence="low",
                    notes=["Upstream data not available (use --refresh-cache to fetch)"]
                )
                diffs.append(diff)
                parse_failures += 1
                continue
            
            # Compute upstream fingerprint
            upstream_fp = self.compute_fingerprint(model_id, upstream_data, "upstream")
            
            # Compare fingerprints
            if local_fp.fingerprint_hash == upstream_fp.fingerprint_hash:
                diff = ModelDiff(
                    model_id=model_id,
                    status="exact_match",
                    local_fingerprint=local_fp,
                    upstream_fingerprint=upstream_fp,
                    diffs={},
                    confidence="high"
                )
                exact_matches += 1
            else:
                # Compute detailed diffs
                detailed_diffs = self._compute_detailed_diffs(local_fp, upstream_fp)
                diff = ModelDiff(
                    model_id=model_id,
                    status="locked_diff" if is_locked else "diff",
                    local_fingerprint=local_fp,
                    upstream_fingerprint=upstream_fp,
                    diffs=detailed_diffs,
                    confidence="high" if source_url else "medium",
                    notes=["Model is locked - report only" if is_locked else "Safe to update"]
                )
                if is_locked:
                    locked_diffs += 1
            
            diffs.append(diff)
        
        self.diffs = diffs
        
        logger.info(f"✅ CHECK complete: {exact_matches} exact matches, {len(diffs) - exact_matches} diffs, {locked_diffs} locked, {parse_failures} parse failures")
        return diffs
    
    def _compute_detailed_diffs(self, local: ModelFingerprint, upstream: ModelFingerprint) -> Dict[str, Any]:
        """Compute detailed differences between two fingerprints."""
        diffs = {}
        
        # Required fields
        if local.required_fields != upstream.required_fields:
            diffs["required_fields"] = {
                "local": sorted(local.required_fields),
                "upstream": sorted(upstream.required_fields)
            }
        
        # Optional fields
        if local.optional_fields != upstream.optional_fields:
            diffs["optional_fields"] = {
                "local": sorted(local.optional_fields),
                "upstream": sorted(upstream.optional_fields)
            }
        
        # Field types
        if local.field_types != upstream.field_types:
            diffs["field_types"] = {
                "local": local.field_types,
                "upstream": upstream.field_types
            }
        
        # Enums
        if local.enums != upstream.enums:
            diffs["enums"] = {
                "local": local.enums,
                "upstream": upstream.enums
            }
        
        # Defaults
        if local.defaults != upstream.defaults:
            diffs["defaults"] = {
                "local": local.defaults,
                "upstream": upstream.defaults
            }
        
        # Pricing
        if local.pricing_credits != upstream.pricing_credits:
            diffs["pricing_credits"] = {
                "local": local.pricing_credits,
                "upstream": upstream.pricing_credits
            }
        
        return diffs
    
    def generate_report(self) -> str:
        """Generate markdown report from diffs."""
        lines = []
        lines.append("# KIE Source-of-Truth Sync Report")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().isoformat()}")
        lines.append(f"**Mode**: CHECK")
        lines.append("")
        
        # Summary
        exact_matches = sum(1 for d in self.diffs if d.status == "exact_match")
        diffs = sum(1 for d in self.diffs if d.status == "diff")
        locked_diffs = sum(1 for d in self.diffs if d.status == "locked_diff")
        parse_failures = sum(1 for d in self.diffs if d.status in ("parse_failure", "missing_upstream"))
        
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Models**: {len(self.diffs)}")
        lines.append(f"- **Exact Matches**: {exact_matches}")
        lines.append(f"- **Diffs (unlocked)**: {diffs}")
        lines.append(f"- **Diffs (locked)**: {locked_diffs}")
        lines.append(f"- **Parse Failures**: {parse_failures}")
        lines.append("")
        
        # Per-model sections
        lines.append("## Per-Model Details")
        lines.append("")
        
        for diff in sorted(self.diffs, key=lambda d: d.model_id):
            lines.append(f"### {diff.model_id}")
            lines.append("")
            lines.append(f"- **Status**: {diff.status}")
            lines.append(f"- **Confidence**: {diff.confidence}")
            if diff.local_fingerprint:
                lines.append(f"- **Local Fingerprint**: `{diff.local_fingerprint.fingerprint_hash}`")
            if diff.upstream_fingerprint:
                lines.append(f"- **Upstream Fingerprint**: `{diff.upstream_fingerprint.fingerprint_hash}`")
            if diff.diffs:
                lines.append("")
                lines.append("**Differences**:")
                lines.append("```json")
                lines.append(json.dumps(diff.diffs, indent=2, ensure_ascii=False))
                lines.append("```")
            if diff.notes:
                lines.append("")
                for note in diff.notes:
                    lines.append(f"- {note}")
            lines.append("")
        
        return "\n".join(lines)
    
    def write_report(self):
        """Write report to file."""
        report_content = self.generate_report()
        self.report_path.write_text(report_content, encoding='utf-8')
        logger.info(f"✅ Report written: {self.report_path}")


def main():
    parser = argparse.ArgumentParser(description="KIE Source-of-Truth Verifier and Sync Tool")
    parser.add_argument("--mode", choices=["check", "update"], default="check", help="Operation mode")
    parser.add_argument("--write", action="store_true", help="Enable writes (UPDATE mode only)")
    parser.add_argument("--refresh-cache", action="store_true", help="Refresh cached snapshots from network")
    parser.add_argument("--add-model", action="store_true", help="Allow adding new models (UPDATE mode only)")
    parser.add_argument("--force-model", action="store_true", help="Force unsafe changes (UPDATE mode only)")
    parser.add_argument("--local-sot", default="models/KIE_SOURCE_OF_TRUTH.json", help="Path to local SOT")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    
    sync = KIERegistrySync(local_sot_path=args.local_sot)
    
    if args.mode == "check":
        diffs = sync.check_all_models()
        sync.write_report()
        logger.info(f"✅ CHECK complete. Report: {sync.report_path}")
        return 0
    elif args.mode == "update":
        if not args.write:
            logger.error("UPDATE mode requires --write flag")
            return 1
        logger.error("UPDATE mode not yet implemented")
        return 1
    else:
        logger.error(f"Unknown mode: {args.mode}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

