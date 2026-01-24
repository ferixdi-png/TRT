#!/usr/bin/env python3
"""
Глубокая проверка архитектурных инвариантов генерации.

Обновлено под текущую архитектуру:
- экран «Задача уже запущена»;
- debounce confirm_generate через submit-lock;
- идемпотентный open_result:<task_id>;
- очистка task_id при терминальных состояниях;
- dedupe по fingerprint/prompt_hash.
"""

from __future__ import annotations

import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Set, Tuple

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BOT_FILE = Path("bot_kie.py")


@dataclass
class CheckIssue:
    level: str  # ERROR / WARNING
    message: str

    def format(self) -> str:
        return f"[{self.level}] {self.message}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(content: str, marker: str, next_markers: Sequence[str]) -> str:
    if marker not in content:
        return ""
    start = content.index(marker) + len(marker)
    tail = content[start:]
    end_positions = [tail.index(m) for m in next_markers if m in tail]
    end = min(end_positions) if end_positions else len(tail)
    return tail[:end]


def _extract_string_literals(block: str) -> List[str]:
    literals: List[str] = []
    for raw in re.findall(r"['\"]([^'\"\\]*(?:\\.[^'\"\\]*)*)['\"]", block):
        if raw:
            literals.append(raw)
    return literals


def _extract_known_prefixes(content: str) -> Set[str]:
    match = re.search(r"KNOWN_CALLBACK_PREFIXES\s*=\s*\((.*?)\)\n\n", content, re.S)
    if not match:
        return set()
    return {s for s in _extract_string_literals(match.group(1)) if s}


def _extract_known_exact(content: str) -> Set[str]:
    match = re.search(r"KNOWN_CALLBACK_EXACT\s*=\s*\{(.*?)\}\n\n", content, re.S)
    if not match:
        return set()
    return {s for s in _extract_string_literals(match.group(1)) if s}


def _extract_callback_data(content: str) -> Set[str]:
    callbacks: Set[str] = set()
    pattern = re.compile(
        r"InlineKeyboardButton\([^)]*callback_data\s*=\s*f?[\"']([^\"']+)[\"']",
        re.S,
    )
    for raw in pattern.findall(content):
        base = raw.split("{", 1)[0].strip()
        if base:
            callbacks.add(base)
    return callbacks


def _extract_button_callback_handlers(content: str) -> Tuple[Set[str], Set[str]]:
    block = ""
    for func_name in ("_button_callback_impl", "button_callback"):
        match = re.search(rf"^async def {func_name}.*?(?=^async def |\Z)", content, re.S | re.M)
        if match:
            block = match.group(0)
            break
    exact = set(re.findall(r"(?:if|elif)\s+data\s*==\s*[\"']([^\"']+)[\"']", block))
    prefix = set(re.findall(r"(?:if|elif)\s+data\.startswith\([\"']([^\"']+)[\"']", block))
    return exact, prefix


def _extract_conversation_patterns(content: str) -> Tuple[Set[str], Set[str]]:
    pattern = re.compile(r"CallbackQueryHandler\([^,]+,\s*pattern\s*=\s*[\"']\^([^\"']+)\$[\"']")
    exact: Set[str] = set()
    prefix: Set[str] = set()
    for token in pattern.findall(content):
        if token.endswith(":"):
            prefix.add(token)
        else:
            exact.add(token)
    return exact, prefix


def _require(content: str, needle: str, message: str, issues: List[CheckIssue]) -> None:
    if needle in content:
        print(f"   [OK] {message}")
    else:
        issues.append(CheckIssue("ERROR", message))
        print(f"   [ERROR] {message}")


def check_confirm_generation_architecture(content: str) -> List[CheckIssue]:
    issues: List[CheckIssue] = []
    confirm_block = _section(content, "async def confirm_generation", ["\nasync def poll_task_status", "\nasync def "])

    print("[ПРОВЕРКА 1] Debounce confirm_generate через submit-lock")
    _require(confirm_block, "_acquire_generation_submit_lock", "submit-lock используется", issues)
    _require(confirm_block, "generation_submit_lock_remaining", "пользователю показывается ожидание debounce", issues)
    print()

    print("[ПРОВЕРКА 2] Экран «Задача уже запущена»")
    _require(content, "Задача уже запущена", "текст экрана «Задача уже запущена» присутствует", issues)
    _require(confirm_block, "task_id_existing = session.get(\"task_id\")", "есть precheck существующего task_id в сессии", issues)
    _require(confirm_block, "reason=\"task_exists_session\"", "precheck ведёт на already-started экран", issues)
    _require(confirm_block, "reason=\"task_exists_active\"", "детект дубля в active_generations ведёт на already-started экран", issues)
    print()

    print("[ПРОВЕРКА 3] Dedupe по fingerprint/prompt_hash")
    _require(content, "def _build_request_fingerprint", "функция fingerprint определена", issues)
    _require(content, "hashlib.sha256", "fingerprint использует sha256", issues)
    _require(confirm_block, "prompt_hash = _build_request_fingerprint", "есть fallback prompt_hash -> fingerprint", issues)
    _require(confirm_block, "get_dedupe_entry(", "dedupe store читается", issues)
    _require(confirm_block, "set_dedupe_entry(", "dedupe store пишется", issues)
    print()

    print("[ПРОВЕРКА 4] Очистка task_id при терминальных состояниях")
    _require(content, "def _clear_session_task_id", "функция очистки task_id определена", issues)
    _require(content, "session.pop(\"task_id\", None)", "task_id удаляется из сессии", issues)
    _require(content, "reason=\"terminal_success\"", "task_id чистится при terminal_success", issues)
    _require(content, "reason=\"terminal_fail\"", "task_id чистится при terminal_fail", issues)
    print()

    print("[ПРОВЕРКА 5] open_result:<task_id> идемпотентен и чистит контекст")
    _require(content, "data.startswith(\"open_result:\")", "open_result:<task_id> обрабатывается в button_callback", issues)
    _require(content, "deliver_job_result(", "open_result пытается доставить результат", issues)
    _require(content, "reason=\"terminal_success_open_result\"", "open_result чистит task_id при успехе", issues)
    _require(content, "reason=\"terminal_fail_open_result\"", "open_result чистит task_id при ошибке", issues)
    print()

    return issues


def validate_prefix_registry(content: str) -> List[CheckIssue]:
    issues: List[CheckIssue] = []
    known_prefixes = _extract_known_prefixes(content)
    known_exact = _extract_known_exact(content)
    callbacks = _extract_callback_data(content)
    handlers_exact, handlers_prefix = _extract_button_callback_handlers(content)
    conv_exact, conv_prefix = _extract_conversation_patterns(content)

    print("[ПРОВЕРКА 6] Валидация зарегистрированных префиксов")
    if not known_prefixes:
        issues.append(CheckIssue("ERROR", "KNOWN_CALLBACK_PREFIXES не найден"))
        print("   [ERROR] KNOWN_CALLBACK_PREFIXES не найден")
        print()
        return issues

    missing_prefixes: Set[str] = set()
    colon_callbacks = sorted(cb for cb in callbacks if ":" in cb)
    for cb in colon_callbacks:
        prefix = cb.split(":", 1)[0] + ":"
        if prefix not in known_prefixes:
            missing_prefixes.add(prefix)

    if missing_prefixes:
        issues.append(
            CheckIssue(
                "ERROR",
                "Не зарегистрированы префиксы: " + ", ".join(sorted(missing_prefixes)),
            )
        )
        print(f"   [ERROR] Не зарегистрированы префиксы: {', '.join(sorted(missing_prefixes))}")
    else:
        print(f"   [OK] Все {len(colon_callbacks)} callback'ов с ':' покрыты KNOWN_CALLBACK_PREFIXES")

    # Проверяем, что важные префиксы покрыты и регистрацией, и обработчиками
    critical_prefixes = {"open_result:", "retry_delivery:", "retry_generate:", "cancel:", "select_model:", "set_param:"}
    for prefix in sorted(critical_prefixes):
        registered = prefix in known_prefixes
        handled = prefix in handlers_prefix or prefix in conv_prefix
        if registered and handled:
            print(f"   [OK] {prefix} зарегистрирован и имеет обработчик")
        elif registered and not handled:
            issues.append(CheckIssue("ERROR", f"{prefix} зарегистрирован, но не найден обработчик"))
            print(f"   [ERROR] {prefix} зарегистрирован, но не найден обработчик")
        else:
            issues.append(CheckIssue("ERROR", f"{prefix} отсутствует в KNOWN_CALLBACK_PREFIXES"))
            print(f"   [ERROR] {prefix} отсутствует в KNOWN_CALLBACK_PREFIXES")
    print()

    print("[ПРОВЕРКА 7] Валидация exact callback'ов")
    critical_exact = {"confirm_generate", "my_generations", "back_to_menu", "cancel", "show_models"}
    for cb in sorted(critical_exact):
        registered = cb in known_exact
        handled = cb in handlers_exact or cb in conv_exact
        if registered and handled:
            print(f"   [OK] {cb} зарегистрирован и имеет обработчик")
        elif registered and not handled:
            issues.append(CheckIssue("ERROR", f"{cb} зарегистрирован, но не найден обработчик"))
            print(f"   [ERROR] {cb} зарегистрирован, но не найден обработчик")
        elif handled and not registered:
            issues.append(CheckIssue("ERROR", f"{cb} обрабатывается, но отсутствует в KNOWN_CALLBACK_EXACT"))
            print(f"   [ERROR] {cb} обрабатывается, но отсутствует в KNOWN_CALLBACK_EXACT")
        else:
            issues.append(CheckIssue("ERROR", f"{cb} не зарегистрирован и не обрабатывается"))
            print(f"   [ERROR] {cb} не зарегистрирован и не обрабатывается")
    print()

    # Дополнительный контроль: все exact callback'и в коде должны быть где-то обработаны
    unhandled_exact: Set[str] = set()
    for cb in callbacks:
        if ":" in cb:
            continue
        if cb in handlers_exact or cb in conv_exact or cb in known_exact:
            continue
        # Допускаем, что некоторые callback'и только регистрируются через prefix
        if any(cb.startswith(prefix) for prefix in known_prefixes):
            continue
        unhandled_exact.add(cb)

    if unhandled_exact:
        issues.append(
            CheckIssue(
                "ERROR",
                "Найдены exact callback'и без регистрации/обработчика: " + ", ".join(sorted(unhandled_exact)[:10]),
            )
        )
        preview = ", ".join(sorted(unhandled_exact)[:10])
        print(f"   [ERROR] Exact callback'и без покрытия (первые 10): {preview}")
    else:
        print("   [OK] Все exact callback'и из callback_data имеют покрытие")
    print()

    return issues


def simulate_callbacks(content: str) -> List[CheckIssue]:
    issues: List[CheckIssue] = []
    known_prefixes = _extract_known_prefixes(content)
    known_exact = _extract_known_exact(content)
    handlers_exact, handlers_prefix = _extract_button_callback_handlers(content)
    conv_exact, conv_prefix = _extract_conversation_patterns(content)

    print("[ПРОВЕРКА 8] E2E-симуляция маршрутизации callback'ов")

    def route_ok(callback_data: str) -> bool:
        if callback_data in handlers_exact or callback_data in conv_exact:
            return True
        if callback_data in known_exact and (
            callback_data in handlers_exact or callback_data in conv_exact or callback_data == "confirm_generate"
        ):
            return True
        if ":" in callback_data:
            prefix = callback_data.split(":", 1)[0] + ":"
            if prefix not in known_prefixes:
                return False
            return prefix in handlers_prefix or prefix in conv_prefix
        return callback_data in known_exact

    scenarios = {
        "confirm_generate": "debounced confirm",
        "open_result:task123": "open_result idempotent",
        "retry_delivery:task123": "retry delivery",
        "retry_generate:": "retry generate",
        "cancel:job123": "cancel by job",
        "select_model:model_x": "select model",
        "set_param:prompt": "set param",
        "my_generations": "status list",
    }

    for callback_data, label in scenarios.items():
        if route_ok(callback_data):
            print(f"   [OK] {label}: {callback_data}")
        else:
            issues.append(CheckIssue("ERROR", f"Маршрут не найден для {callback_data}"))
            print(f"   [ERROR] {label}: {callback_data}")
    print()

    return issues


def main() -> int:
    if not BOT_FILE.exists():
        print(f"[ERROR] Файл не найден: {BOT_FILE}")
        return 1

    content = _read_text(BOT_FILE)

    print("=" * 80)
    print("DEEP GENERATION CHECK — ARCHITECTURE")
    print("=" * 80)
    print()

    issues: List[CheckIssue] = []
    issues.extend(check_confirm_generation_architecture(content))
    issues.extend(validate_prefix_registry(content))
    issues.extend(simulate_callbacks(content))

    print("=" * 80)
    print("ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 80)

    if not issues:
        print("[SUCCESS] Все архитектурные проверки пройдены.")
        return 0

    errors = [i for i in issues if i.level == "ERROR"]
    warnings = [i for i in issues if i.level != "ERROR"]

    print(f"[FAIL] Найдено проблем: {len(issues)} (errors={len(errors)}, warnings={len(warnings)})")
    for issue in issues[:40]:
        print("  ", issue.format())
    if len(issues) > 40:
        print(f"   ... и ещё {len(issues) - 40}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
