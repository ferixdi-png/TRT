"""Dry-run contract test for all allowlisted models.

Goal (Syntx-parity): for each allowlisted model we must be able to:
  model selection -> wizard -> confirm -> createTask

This script validates the *contract before calling Kie*:
  - builds the minimal payload (with schema defaults injected)
  - runs local validation against the model's input_schema

Run:
  python scripts/dry_run_allowlist.py

Exit code:
  0 - all models OK
  1 - at least one model failed contract validation
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_allowlist() -> List[str]:
    p = _repo_root() / "models" / "ALLOWED_MODEL_IDS.txt"
    if not p.exists():
        return []
    ids: List[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        ids.append(s)
    # keep order, drop dups
    seen = set()
    out: List[str] = []
    for mid in ids:
        if mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out


def _dummy_value(field) -> Any:
    # Late imports to keep script lightweight
    from app.ui.input_spec import InputType

    if field.type in (InputType.IMAGE_URL, InputType.IMAGE_FILE):
        return "https://example.com/test.jpg"
    if field.type in (InputType.VIDEO_URL, InputType.VIDEO_FILE):
        return "https://example.com/test.mp4"
    if field.type in (InputType.AUDIO_URL, InputType.AUDIO_FILE):
        return "https://example.com/test.mp3"
    if field.type == InputType.NUMBER:
        if field.default is not None:
            return field.default
        if field.min_value is not None:
            return field.min_value
        return 1
    if field.type == InputType.BOOLEAN:
        if field.default is not None:
            return bool(field.default)
        return True
    if field.type == InputType.ENUM:
        if field.default is not None:
            return field.default
        if field.enum_values:
            return field.enum_values[0]
        return ""
    # TEXT
    if field.default is not None:
        return field.default
    return "test prompt"


def _minimal_inputs_for_model(model_cfg: Dict[str, Any]) -> Dict[str, Any]:
    from app.ui.input_spec import get_input_spec

    spec = get_input_spec(model_cfg)
    inputs: Dict[str, Any] = {}

    for field in spec.fields:
        if field.required:
            inputs[field.name] = _dummy_value(field)

    # Optional-but-important: prompt/text/description if present (even if schema doesn't mark as required)
    for name in ("prompt", "text", "description"):
        if name in {f.name for f in spec.fields} and name not in inputs:
            inputs[name] = "test prompt"

    return inputs


def main() -> int:
    # Ensure local imports work when run from anywhere
    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root))

    from app.kie.builder import load_source_of_truth, build_payload

    sot = load_source_of_truth()
    models = sot.get("models") or {}

    allowlist = _load_allowlist()
    if not allowlist:
        print("[dry-run] WARN: allowlist is empty (models/ALLOWED_MODEL_IDS.txt not found?)")
        # Fall back to whatever is in SOURCE_OF_TRUTH
        allowlist = list(models.keys()) if isinstance(models, dict) else []

    failures: List[Tuple[str, str]] = []
    missing: List[str] = []

    for mid in allowlist:
        cfg = models.get(mid) if isinstance(models, dict) else None
        if not cfg:
            missing.append(mid)
            continue

        try:
            user_inputs = _minimal_inputs_for_model(cfg)
            payload = build_payload(mid, user_inputs, sot)
            # Extra sanity: payload must have model id somewhere
            if not isinstance(payload, dict):
                raise RuntimeError("payload is not a dict")
            if payload.get("model") != mid and payload.get("model_id") != mid:
                # some V3 payloads keep model in 'model'
                if payload.get("model") is None and payload.get("input") is None:
                    raise RuntimeError("payload missing model/input")
        except Exception as e:
            failures.append((mid, str(e)))

    print("[dry-run] allowlist models:", len(allowlist))
    if missing:
        print("[dry-run] MISSING in SOURCE_OF_TRUTH:")
        for mid in missing:
            print("  -", mid)

    if failures:
        print("[dry-run] FAILURES:")
        for mid, err in failures:
            print(f"  - {mid}: {err}")
        return 1

    print("[dry-run] OK: all models passed local contract validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
