import os
from typing import Optional


def get_public_base_url() -> Optional[str]:
    """Best-effort public base URL detection.

    Matches the env-var order used by the webhook server.
    Returns a URL without the trailing slash.
    """

    for key in ("WEBHOOK_BASE_URL", "RENDER_EXTERNAL_URL", "PUBLIC_URL", "SERVICE_URL"):
        v = os.getenv(key)
        if v:
            return v.rstrip("/")
    return None
