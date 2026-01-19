"""Normalize KIE result URLs for downstream delivery."""
from __future__ import annotations

import os
from typing import Iterable, List, Optional

from app.observability.structured_logs import log_structured_event


class ResultUrlNormalizationError(ValueError):
    """Raised when a result URL cannot be normalized safely."""


def _resolve_base_url(base_url: Optional[str]) -> str:
    resolved = (base_url or os.getenv("KIE_RESULT_CDN_BASE_URL", "")).strip()
    return resolved.rstrip("/")


def normalize_result_url(
    raw_url: str,
    *,
    base_url: Optional[str] = None,
    correlation_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stage: str = "KIE_PARSE",
) -> str:
    raw_value = (raw_url or "").strip()
    resolved_base = _resolve_base_url(base_url)
    normalized_url: Optional[str]

    if raw_value.startswith("http://") or raw_value.startswith("https://"):
        normalized_url = raw_value
    elif raw_value.startswith("//"):
        normalized_url = f"https:{raw_value}"
    elif raw_value.startswith("/"):
        if not resolved_base:
            log_structured_event(
                correlation_id=correlation_id,
                action="URL_NORMALIZE",
                action_path="url_normalizer.normalize_result_url",
                model_id=model_id,
                stage=stage,
                outcome="failed",
                error_code="URL_BASE_MISSING",
                fix_hint="Настройте KIE_RESULT_CDN_BASE_URL для относительных URL.",
                param={"raw_url": raw_value, "normalized_url": None},
            )
            raise ResultUrlNormalizationError("Relative URL requires base domain configuration")
        normalized_url = f"{resolved_base}{raw_value}"
    else:
        normalized_url = raw_value

    log_structured_event(
        correlation_id=correlation_id,
        action="URL_NORMALIZE",
        action_path="url_normalizer.normalize_result_url",
        model_id=model_id,
        stage=stage,
        outcome="normalized",
        param={"raw_url": raw_value, "normalized_url": normalized_url},
    )
    return normalized_url


def normalize_result_urls(
    urls: Iterable[str],
    *,
    base_url: Optional[str] = None,
    correlation_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stage: str = "KIE_PARSE",
) -> List[str]:
    normalized: List[str] = []
    for raw_url in urls:
        if not raw_url:
            continue
        normalized.append(
            normalize_result_url(
                raw_url,
                base_url=base_url,
                correlation_id=correlation_id,
                model_id=model_id,
                stage=stage,
            )
        )
    return normalized
