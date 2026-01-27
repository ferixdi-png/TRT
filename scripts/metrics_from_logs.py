#!/usr/bin/env python3
"""Compute p50/p95/p99 latencies from STRUCTURED_LOG lines."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


FIELDS = [
    "ack_ms",
    "handler_total_ms",
    "tg_send_ms",
    "kie_call_ms",
    "db_query_ms",
    "lock_wait_ms_total",
]


def _iter_lines(paths: List[Path]) -> Iterable[str]:
    if not paths:
        yield from []
        return
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                yield line.rstrip()


def _parse_structured_logs(lines: Iterable[str]) -> List[dict]:
    entries = []
    for line in lines:
        if "STRUCTURED_LOG" not in line:
            continue
        try:
            _, payload = line.split("STRUCTURED_LOG", 1)
        except ValueError:
            continue
        payload = payload.strip()
        if not payload:
            continue
        try:
            entries.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return entries


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(math.ceil(pct / 100 * len(ordered))) - 1))
    return float(ordered[idx])


def _summarize(entries: List[dict]) -> Dict[str, Dict[str, Optional[float]]]:
    results: Dict[str, Dict[str, Optional[float]]] = {}
    for field in FIELDS:
        values = []
        for entry in entries:
            value = entry.get(field)
            if isinstance(value, (int, float)):
                values.append(float(value))
        results[field] = {
            "p50": _percentile(values, 50),
            "p95": _percentile(values, 95),
            "p99": _percentile(values, 99),
        }
    return results


def _format_table(summary: Dict[str, Dict[str, Optional[float]]]) -> str:
    lines = ["| metric | p50 | p95 | p99 |", "| --- | --- | --- | --- |"]
    for field, stats in summary.items():
        def _fmt(value: Optional[float]) -> str:
            return f"{value:.1f}ms" if value is not None else "n/a"

        lines.append(
            f"| {field} | {_fmt(stats['p50'])} | {_fmt(stats['p95'])} | {_fmt(stats['p99'])} |"
        )
    return "\n".join(lines)


def _update_report(report_path: Path, summary_table: str) -> None:
    marker_start = "<!-- METRICS_START -->"
    marker_end = "<!-- METRICS_END -->"
    content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    new_block = f"{marker_start}\n{summary_table}\n{marker_end}\n"
    if marker_start in content and marker_end in content:
        before = content.split(marker_start)[0]
        after = content.split(marker_end)[-1]
        report_path.write_text(f"{before}{new_block}{after}".strip() + "\n", encoding="utf-8")
        return
    report_path.write_text(content.rstrip() + "\n\n" + new_block, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute latency percentiles from STRUCTURED_LOG lines.")
    parser.add_argument("paths", nargs="*", type=Path, help="Log files to parse")
    parser.add_argument("--report", type=Path, help="Optional TRT_REPORT.md path to update")
    args = parser.parse_args()

    entries = _parse_structured_logs(_iter_lines(args.paths))
    summary = _summarize(entries)
    table = _format_table(summary)
    print(table)
    if args.report:
        _update_report(args.report, table)


if __name__ == "__main__":
    main()
