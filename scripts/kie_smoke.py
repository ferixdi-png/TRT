#!/usr/bin/env python3
"""Smoke-test Kie.ai createTask contract for free-tier models.

Usage:
  python scripts/kie_smoke.py --free-tier
  python scripts/kie_smoke.py --model z-image --prompt "котик"
  python scripts/kie_smoke.py --image-url https://... --audio-url https://...

Requires:
  - KIE_API_KEY
  - Optional: KIE_SMOKE_IMAGE_URL / KIE_SMOKE_AUDIO_URL / KIE_SMOKE_VIDEO_URL
"""
from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any, Dict, List, Tuple

from app.api.kie_client import KieApiClient
from app.kie.builder import build_payload, load_source_of_truth
from app.payments.pricing_contract import get_pricing_contract
from app.pricing.free_tier import get_free_tier_models


def _load_registry() -> Dict[str, Any]:
    return load_source_of_truth()


def _compute_free_tier_ids(models: Dict[str, Any]) -> List[str]:
    pricing_contract = get_pricing_contract()
    pricing_contract.load_truth()
    pricing_map = {
        model_id: rub for model_id, (_, rub) in pricing_contract._pricing_map.items()
    }
    models_dict = dict(models.items()) if hasattr(models, "items") else {}
    free_ids, _ = get_free_tier_models(
        models_dict,
        pricing_map,
        override_env=os.getenv("FREE_TIER_MODEL_IDS"),
        count=5,
    )
    return free_ids


def _required_fields(schema: Dict[str, Any]) -> List[str]:
    if not isinstance(schema, dict):
        return []
    if "input" in schema and isinstance(schema.get("input"), dict):
        schema = schema["input"]
    if schema.get("type") == "object" and isinstance(schema.get("required"), list):
        return list(schema.get("required") or [])
    if "properties" in schema:
        required = schema.get("required", []) or []
        if isinstance(required, list):
            return list(required)
    if isinstance(schema, dict) and schema and all(isinstance(v, dict) for v in schema.values()):
        return [k for k, v in schema.items() if v.get("required") is True]
    return []


def _build_min_inputs(
    required: List[str],
    prompt: str,
    media_urls: Dict[str, str],
) -> Tuple[Dict[str, Any], List[str]]:
    inputs: Dict[str, Any] = {}
    missing: List[str] = []
    for field in required:
        if field == "prompt":
            inputs["prompt"] = prompt
        elif field == "image_url":
            if media_urls.get("image_url"):
                inputs["image_url"] = media_urls["image_url"]
            else:
                missing.append(field)
        elif field == "audio_url":
            if media_urls.get("audio_url"):
                inputs["audio_url"] = media_urls["audio_url"]
            else:
                missing.append(field)
        elif field == "video_url":
            if media_urls.get("video_url"):
                inputs["video_url"] = media_urls["video_url"]
            else:
                missing.append(field)
        else:
            missing.append(field)
    if not required and prompt:
        inputs["prompt"] = prompt
    return inputs, missing


def _callback_url() -> str | None:
    base_url = os.getenv("WEBHOOK_BASE_URL") or os.getenv("PUBLIC_BASE_URL") or ""
    base_url = base_url.rstrip("/")
    if not base_url:
        return None
    return f"{base_url}/kie/callback"


def _table(rows: List[Tuple[str, str, str]]) -> None:
    headers = ("MODEL", "STATUS", "DETAIL")
    width_model = max(len(headers[0]), *(len(r[0]) for r in rows)) if rows else len(headers[0])
    width_status = max(len(headers[1]), *(len(r[1]) for r in rows)) if rows else len(headers[1])
    print(f"{headers[0]:<{width_model}}  {headers[1]:<{width_status}}  {headers[2]}")
    print(f"{'-' * width_model}  {'-' * width_status}  {'-' * len(headers[2])}")
    for model_id, status, detail in rows:
        print(f"{model_id:<{width_model}}  {status:<{width_status}}  {detail}")


async def _run_smoke(
    models: List[str],
    prompt: str,
    media_urls: Dict[str, str],
    create_only: bool,
) -> int:
    client = KieApiClient()
    registry = _load_registry()
    models_dict = registry.get("models", {})
    callback_url = _callback_url()
    failures = 0
    rows: List[Tuple[str, str, str]] = []

    print("Endpoint: POST /api/v1/jobs/createTask")
    if not callback_url:
        print("WARN: callBackUrl not set (missing WEBHOOK_BASE_URL or PUBLIC_BASE_URL)")

    for model_id in models:
        model = models_dict.get(model_id) if hasattr(models_dict, "get") else None
        if not isinstance(model, dict):
            rows.append((model_id, "SKIP", "not found in registry"))
            continue

        required = _required_fields(model.get("input_schema", {}))
        inputs, missing = _build_min_inputs(required, prompt, media_urls)
        if missing:
            rows.append((model_id, "SKIP", f"missing inputs: {', '.join(missing)}"))
            continue

        try:
            payload = build_payload(model_id, inputs, registry)
        except Exception as exc:
            failures += 1
            rows.append((model_id, "FAIL", f"build_payload error: {exc}"))
            continue

        try:
            response = await client.create_task(payload, callback_url=callback_url)
        except Exception as exc:
            failures += 1
            rows.append((model_id, "FAIL", f"createTask exception: {exc}"))
            continue

        task_id = None
        code = None
        msg = None
        if isinstance(response, dict):
            task_id = response.get("taskId") or (response.get("data") or {}).get("taskId")
            code = response.get("code")
            msg = response.get("msg")
        if task_id:
            rows.append((model_id, "OK", f"taskId={task_id}"))
        else:
            failures += 1
            detail = "no taskId in response"
            if code is not None or msg:
                detail = f"code={code} msg={msg or 'n/a'}"
            rows.append((model_id, "FAIL", detail))

    _table(rows)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Kie createTask for free-tier models.")
    parser.add_argument("--free-tier", action="store_true", help="Use auto-derived FREE tier list.")
    parser.add_argument("--model", action="append", default=[], help="Model ID to test (repeatable).")
    parser.add_argument("--prompt", default="котик", help="Prompt to use for text-based models.")
    parser.add_argument("--image-url", default=os.getenv("KIE_SMOKE_IMAGE_URL", ""), help="Image URL for image models.")
    parser.add_argument("--audio-url", default=os.getenv("KIE_SMOKE_AUDIO_URL", ""), help="Audio URL for audio models.")
    parser.add_argument("--video-url", default=os.getenv("KIE_SMOKE_VIDEO_URL", ""), help="Video URL for video models.")
    parser.add_argument("--create-only", action="store_true", help="Only createTask and taskId.")
    args = parser.parse_args()

    if not os.getenv("KIE_API_KEY"):
        raise SystemExit("KIE_API_KEY is required for scripts/kie_smoke.py")

    registry = _load_registry()
    models_dict = registry.get("models", {})

    if args.model:
        models = args.model
    elif args.free_tier or not args.model:
        models = _compute_free_tier_ids(models_dict)
    else:
        models = []

    media_urls = {
        "image_url": args.image_url,
        "audio_url": args.audio_url,
        "video_url": args.video_url,
    }
    failures = asyncio.run(_run_smoke(models, args.prompt, media_urls, args.create_only))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
