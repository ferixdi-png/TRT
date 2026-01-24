#!/usr/bin/env python3
"""Offline smoke for all SSOT models."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from telegram import InputFile

from app.generations.failure_ui import build_kie_fail_ui
from app.generations.media_pipeline import resolve_and_prepare_telegram_payload
from app.kie_catalog import get_model_map, ModelSpec


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample.txt"


class DummyResponse:
    def __init__(self, *, headers=None, body=b"", history=None, content_length=None):
        self.headers = headers or {}
        self._body = body
        self.history = history or []
        self.content_length = content_length

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySession:
    def __init__(self, head_response: DummyResponse, get_response: DummyResponse):
        self._head_response = head_response
        self._get_response = get_response

    def head(self, *args, **kwargs):
        return self._head_response

    def get(self, *args, **kwargs):
        return self._get_response


def _build_min_params(spec: ModelSpec) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for name, schema in spec.schema_properties.items():
        if not schema.get("required", False):
            continue
        param_type = schema.get("type", "string")
        enum_values = schema.get("enum") or schema.get("values") or []
        if isinstance(enum_values, dict):
            enum_values = list(enum_values.values())
        if isinstance(enum_values, list) and enum_values and isinstance(enum_values[0], dict):
            enum_values = [value.get("value") or value.get("id") or value.get("name") for value in enum_values]
            enum_values = [value for value in enum_values if value is not None]
        if param_type == "enum" and enum_values:
            params[name] = enum_values[0]
        elif param_type == "boolean":
            params[name] = True
        elif param_type in {"number", "integer", "float"}:
            params[name] = schema.get("default", 1) or schema.get("minimum", 1) or 1
        elif param_type in {"array", "list"}:
            params[name] = ["test"]
        elif param_type in {"file", "image", "audio", "video"} or schema.get("format") in {"file", "binary"}:
            params[name] = str(FIXTURE_PATH)
        else:
            params[name] = "test"
    return params


def _media_content_type(media_kind: str) -> str:
    if media_kind == "image":
        return "image/png"
    if media_kind == "video":
        return "video/mp4"
    if media_kind in {"audio", "voice"}:
        return "audio/mpeg"
    return "application/octet-stream"


async def _run_media_check(spec: ModelSpec, media_kind: str, style: str) -> bool:
    urls: List[str] = []
    text = None

    if media_kind == "text":
        text = "test"
    else:
        urls = [f"https://example.com/{spec.id}/{style}"]

    if style == "direct":
        content_type = _media_content_type(media_kind)
        head = DummyResponse(headers={"Content-Type": content_type}, content_length=1024)
        get = DummyResponse(headers={"Content-Type": content_type}, body=b"data")
    elif style == "html":
        head = DummyResponse(headers={"Content-Type": "text/html"}, content_length=1024)
        get = DummyResponse(headers={"Content-Type": _media_content_type(media_kind)}, body=b"data")
    else:  # unknown
        head = DummyResponse(headers={"Content-Type": "application/octet-stream"}, content_length=1024)
        get = DummyResponse(headers={"Content-Type": "application/octet-stream"}, body=b"data")

    session = DummySession(head, get)
    tg_method, payload = await resolve_and_prepare_telegram_payload(
        {"urls": urls, "text": text},
        "corr-smoke",
        media_kind,
        kie_client=None,
        http_client=session,
    )

    if media_kind == "text":
        return tg_method == "send_message"
    if style == "unknown":
        return tg_method == "send_document"
    if style == "html":
        key = {
            "send_photo": "photo",
            "send_video": "video",
            "send_audio": "audio",
            "send_voice": "voice",
        }.get(tg_method)
        return key in payload and isinstance(payload[key], InputFile)
    return tg_method in {"send_photo", "send_video", "send_audio", "send_voice", "send_document"}


def _validate_ssot_counts() -> Tuple[bool, int, int, int]:
    root = Path(__file__).resolve().parents[1]
    registry_path = root / "models" / "kie_models.yaml"
    pricing_path = root / "app" / "kie_catalog" / "models_pricing.yaml"

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    pricing = yaml.safe_load(pricing_path.read_text(encoding="utf-8")) or {}
    models_count = len((registry.get("models") or {}))
    pricing_count = len((pricing.get("models") or []))
    meta_total = registry.get("meta", {}).get("total_models")
    if isinstance(meta_total, bool):
        meta_total = None
    expected_total = meta_total if isinstance(meta_total, int) else models_count

    is_valid = models_count == expected_total and pricing_count == expected_total
    return is_valid, expected_total, models_count, pricing_count


async def main() -> int:
    if not FIXTURE_PATH.exists():
        print(f"Missing fixture file: {FIXTURE_PATH}")
        return 1

    ssot_valid, expected_total, models_count, pricing_count = _validate_ssot_counts()
    if not ssot_valid:
        print(
            "SSOT validation failed "
            f"(expected {expected_total}, registry={models_count}, pricing={pricing_count})"
        )
        return 1

    model_map = get_model_map()
    ok = 0
    failed = 0
    for spec in model_map.values():
        _build_min_params(spec)
        media_kind = spec.output_media_type or spec.model_type or "document"
        media_kind = media_kind if media_kind != "file" else "document"
        for style in ("direct", "html", "unknown"):
            success = await _run_media_check(spec, media_kind, style)
            if success:
                ok += 1
            else:
                failed += 1
        fail_text, _ = build_kie_fail_ui("corr-smoke", spec.id)
        if "correlation_id=corr-smoke" in fail_text:
            ok += 1
        else:
            failed += 1

    print(f"smoke_all_models_offline: ok={ok} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
