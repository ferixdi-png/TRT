"""Canonical config loader for shared settings."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalConfig:
    kie_api_url: str
    kie_api_key: str
    storage_backend: str

    @classmethod
    def from_env(cls) -> "CanonicalConfig":
        return cls(
            kie_api_url=os.getenv("KIE_API_URL", "https://api.kie.ai").strip(),
            kie_api_key=os.getenv("KIE_API_KEY", "").strip(),
            storage_backend=os.getenv("STORAGE_BACKEND", "github").strip(),
        )


def load_canonical_config() -> CanonicalConfig:
    return CanonicalConfig.from_env()
