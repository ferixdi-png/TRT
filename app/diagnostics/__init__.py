"""Diagnostics package."""

from app.diagnostics.boot import (
    format_boot_report,
    get_cached_boot_report,
    get_cached_boot_report_text,
    run_boot_diagnostics,
)

__all__ = [
    "format_boot_report",
    "get_cached_boot_report",
    "get_cached_boot_report_text",
    "run_boot_diagnostics",
]
