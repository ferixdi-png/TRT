"""Normalize KIE result URLs for downstream delivery."""
from __future__ import annotations

import os
from urllib.parse import urlparse, urlunsplit
from typing import Iterable, List, Optional

from app.observability.structured_logs import log_structured_event


class ResultUrlNormalizationError(ValueError):
    """Raised when a result URL cannot be normalized safely."""


def _resolve_base_url(base_url: Optional[str]) -> str:
    resolved = (base_url or os.getenv("KIE_RESULT_CDN_BASE_URL", "")).strip()
    return resolved.rstrip("/")


def _extract_host_from_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.netloc:
        return parsed.netloc
    if "://" not in value and value.strip():
        return value.strip()
    return None


def _resolve_fallback_host(
    *,
    base_url: Optional[str],
    record_info: Optional[dict],
) -> Optional[str]:
    candidates = [
        base_url,
        os.getenv("KIE_API_URL", ""),
    ]
    record_info = record_info or {}
    for key in (
        "baseUrl",
        "base_url",
        "cdnBaseUrl",
        "cdn_base_url",
        "resultBaseUrl",
        "result_base_url",
        "host",
        "hostname",
        "domain",
    ):
        candidates.append(record_info.get(key))
    for candidate in candidates:
        host = _extract_host_from_value(candidate)
        if host:
            return host
    return None


def is_valid_result_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_result_url(
    raw_url: str,
    *,
    base_url: Optional[str] = None,
    record_info: Optional[dict] = None,
    correlation_id: Optional[str] = None,
    model_id: Optional[str] = None,
    stage: str = "KIE_PARSE",
) -> str:
    raw_value = (raw_url or "").strip()
    http_index = raw_value.find("http://")
    https_index = raw_value.find("https://")
    http_candidates = [idx for idx in (http_index, https_index) if idx != -1]
    if http_candidates:
        first_index = min(http_candidates)
        if first_index > 0:
            raw_value = raw_value[first_index:]
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
                waiting_for="URL_NORMALIZE",
                outcome="failed",
                error_code="URL_BASE_MISSING",
                fix_hint="Настройте KIE_RESULT_CDN_BASE_URL для относительных URL.",
                param={"raw_url": raw_value, "normalized_url": None},
            )
            raise ResultUrlNormalizationError("Relative URL requires base domain configuration")
        normalized_url = f"{resolved_base}{raw_value}"
    else:
        normalized_url = raw_value

    parsed = urlparse(normalized_url)
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        fallback_host = _resolve_fallback_host(base_url=resolved_base, record_info=record_info)
        if fallback_host:
            normalized_url = urlunsplit(
                (parsed.scheme, fallback_host, parsed.path or "/", parsed.query, parsed.fragment)
            )
            parsed = urlparse(normalized_url)

    log_structured_event(
        correlation_id=correlation_id,
        action="URL_NORMALIZE",
        action_path="url_normalizer.normalize_result_url",
        model_id=model_id,
        stage=stage,
        outcome="normalized",
        param={"raw_url": raw_value, "normalized_url": normalized_url},
    )
    if not is_valid_result_url(normalized_url):
        log_structured_event(
            correlation_id=correlation_id,
            action="URL_NORMALIZE",
            action_path="url_normalizer.normalize_result_url",
            model_id=model_id,
            stage=stage,
            waiting_for="URL_NORMALIZE",
            outcome="failed",
            error_code="INVALID_RESULT_URL",
            fix_hint="check_kie_response_url_fields",
            param={"raw_url": raw_value, "normalized_url": normalized_url},
        )
        raise ResultUrlNormalizationError("INVALID_RESULT_URL")
    return normalized_url


def normalize_result_urls(
    urls: Iterable[str],
    *,
    base_url: Optional[str] = None,
    record_info: Optional[dict] = None,
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
                record_info=record_info,
                correlation_id=correlation_id,
                model_id=model_id,
                stage=stage,
            )
        )
    return normalized
