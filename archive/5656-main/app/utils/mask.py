"""Masking helpers for logs."""

def mask(value: str) -> str:
    if not value:
        return "[EMPTY]"
    if len(value) <= 8:
        return "****"
    return f"{value[:2]}...{value[-2:]}"
