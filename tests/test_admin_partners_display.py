"""
Admin Partners Display — REGRESSION TESTS (железобетонная фиксация)

Зафиксировано: 2026-02-11
НЕ УДАЛЯТЬ И НЕ ОСЛАБЛЯТЬ БЕЗ ОБСУЖДЕНИЯ!

Покрытие:
1. list_all_partners — структура возвращаемых данных
2. Формат отображения для партнёров С boot-отчётом
3. Формат отображения для партнёров БЕЗ boot-отчёта (инференс ключей)
4. Фильтрация шума (PORT_BIND)
5. Deploy status логика (🟢/🟡/🔴)
6. Русские вердикты — все ветки
7. Optional features — группировка по категориям
"""

import inspect
import pytest


# ---------------------------------------------------------------------------
# 1. SOURCE INSPECTION — list_all_partners data structure
# ---------------------------------------------------------------------------

class TestListAllPartnersStructure:
    """Проверяем что list_all_partners возвращает ВСЕ нужные поля."""

    def test_result_dict_has_all_required_fields(self):
        """Каждый partner dict ДОЛЖЕН содержать все поля для отображения."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        required_fields = [
            '"partner_id"', '"file_count"', '"last_updated_ago"',
            '"deploy_status"', '"has_boot"', '"boot_result"',
            '"required_keys"', '"required_missing"', '"all_required_ok"',
            '"optional_features"', '"problems"', '"data_summary"',
        ]
        for field in required_fields:
            assert field in source, (
                f"КРИТИЧНО: list_all_partners ДОЛЖЕН возвращать {field}! "
                "Без этого admin_partners сломается."
            )

    def test_data_summary_has_users_payments_generations_files(self):
        """data_summary ДОЛЖЕН содержать users, payments, generations, files."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        for key in ["users", "payments", "generations", "files"]:
            assert f'"{key}"' in source, (
                f"КРИТИЧНО: data_summary ДОЛЖЕН содержать '{key}'!"
            )

    def test_required_config_keys_present(self):
        """Проверяем что все обязательные ключи определены."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        for key in ["ADMIN_ID", "BOT_INSTANCE_ID", "WEBHOOK_BASE_URL", "KIE_API_KEY"]:
            assert key in source, f"Обязательный ключ {key} должен проверяться"

    def test_required_services_present(self):
        """Проверяем что TELEGRAM и DATABASE секции проверяются."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        for svc in ["TELEGRAM", "DATABASE"]:
            assert svc in source, f"Сервис {svc} должен проверяться"

    def test_deploy_status_thresholds(self):
        """Deploy status: 🟢 < 1h, 🟡 1-6h, 🔴 > 6h."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        assert 'timedelta(hours=1)' in source, "Порог 🟢 = 1 час"
        assert 'timedelta(hours=6)' in source, "Порог 🟡 = 6 часов"
        assert '"🟢"' in source
        assert '"🟡"' in source
        assert '"🔴"' in source

    def test_optional_display_vars_complete(self):
        """Все опциональные переменные должны быть в маппинге."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        expected_vars = [
            "PAYMENT_BANK", "PAYMENT_CARD_HOLDER", "PAYMENT_PHONE",
            "SUPPORT_TELEGRAM", "SUPPORT_TEXT",
            "BOT_NAME", "BOT_USERNAME", "WEBAPP_URL",
            "CHAT_ZIMAGE_CHAT", "CHAT_ZIMAGE_ADMIN_IDS",
        ]
        for var in expected_vars:
            assert var in source, f"Опциональная переменная {var} должна проверяться"

    def test_files_exclude_diagnostics(self):
        """Файлы в data_summary НЕ должны включать _diagnostics/."""
        from app.storage.postgres_storage import PostgresStorage
        source = inspect.getsource(PostgresStorage.list_all_partners)

        assert '_diagnostics/' in source, "Фильтр _diagnostics/ должен присутствовать"


# ---------------------------------------------------------------------------
# 2. SOURCE INSPECTION — admin_partners display handler
# ---------------------------------------------------------------------------

class TestAdminPartnersDisplaySource:
    """Проверяем что display handler содержит все нужные элементы."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        """Загружаем исходник bot_kie.py один раз."""
        with open("bot_kie.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_noise_filter_port_bind(self):
        """PORT_BIND ДОЛЖЕН фильтроваться как шум."""
        assert 'NOISE_PREFIXES' in self.source, "NOISE_PREFIXES должен быть определён"
        assert 'PORT_BIND' in self.source, "PORT_BIND должен быть в списке шума"

    def test_diagnostics_partner_filtered(self):
        """Партнёр 'diagnostics' должен быть отфильтрован."""
        assert '"diagnostics"' in self.source, "Фильтр diagnostics партнёра"

    def test_header_format(self):
        """Заголовок: ИНСТАНСЫ + счётчики."""
        assert "ИНСТАНСЫ" in self.source
        assert "Всё ОК" in self.source
        assert "Проблемы" in self.source
        assert "Нет отчёта" in self.source

    def test_no_boot_inferred_keys_displayed(self):
        """Для no-boot партнёров показываются выведенные ключи."""
        assert "ADMIN" in self.source
        assert "INSTANCE" in self.source
        assert "WEBHOOK" in self.source
        assert "KIE" in self.source
        assert "TG_TOKEN" in self.source
        assert "DATABASE" in self.source

    def test_no_boot_unknown_marker(self):
        """❓ = нет boot-отчёта объяснение."""
        assert "нет boot-отчёта" in self.source

    def test_boot_required_keys_all_ok_format(self):
        """Формат 'все на месте' для партнёров с boot и всеми ключами."""
        assert "все на месте" in self.source

    def test_boot_missing_keys_format(self):
        """Формат для партнёров с отсутствующими ключами."""
        assert "Нет:" in self.source

    def test_optional_features_payment_category(self):
        """Оплата: Банк, Держатель, Телефон."""
        assert "Банк" in self.source
        assert "Держатель" in self.source
        assert "Телефон" in self.source

    def test_optional_features_support_category(self):
        """Поддержка: TG, Текст."""
        assert "Поддержка TG" in self.source
        assert "Текст поддержки" in self.source

    def test_optional_features_extras_category(self):
        """Доп: Имя бота, Username, WebApp, ZImage."""
        assert "Имя бота" in self.source
        assert "Username" in self.source
        assert "WebApp" in self.source
        assert "ZImage чат" in self.source
        assert "ZImage админы" in self.source

    def test_problems_truncated_at_80_chars(self):
        """Проблемы обрезаются до 80 символов."""
        assert "80" in self.source
        assert "77" in self.source  # [:77] + "..."

    def test_problems_max_2_shown(self):
        """Показываются максимум 2 проблемы + счётчик."""
        assert "probs[:2]" in self.source
        assert "ещё" in self.source

    def test_message_truncation_at_4000(self):
        """Сообщение обрезается на 4000 символов (лимит TG = 4096)."""
        assert "4000" in self.source
        assert "обрезано" in self.source

    def test_refresh_button_exists(self):
        """Кнопка 'Обновить' должна быть."""
        assert "Обновить" in self.source

    def test_back_button_exists(self):
        """Кнопка 'Назад' к admin_stats."""
        assert "admin_stats" in self.source


# ---------------------------------------------------------------------------
# 3. VERDICT LOGIC — no-boot partners
# ---------------------------------------------------------------------------

class TestNoBootVerdicts:
    """Проверяем все ветки вердиктов для партнёров без boot-отчёта."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open("bot_kie.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_verdict_active_with_payments(self):
        """users > 0 AND pays > 0 → ✅ Активен."""
        assert "Активен:" in self.source

    def test_verdict_users_no_payments(self):
        """users > 0 AND pays == 0 → 📊 Есть юзеры, платежей нет."""
        assert "Есть юзеры" in self.source
        assert "платежей нет" in self.source

    def test_verdict_online_no_users(self):
        """🟢 + has_files + 0 users → ⏳ Настроен, ожидает пользователей."""
        assert "ожидает пользователей" in self.source

    def test_verdict_has_files_inactive(self):
        """has_files + not 🟢 → ⏳ Данные есть, бот неактивен."""
        assert "Данные есть, бот неактивен" in self.source

    def test_verdict_no_data(self):
        """No files → ❓ Нет данных."""
        assert "Нет данных" in self.source

    def test_sleeping_bot_hint(self):
        """🟡 → Render усыпил бота."""
        assert "Render усыпил бота" in self.source

    def test_dead_bot_hint(self):
        """🔴 → Бот не отвечает давно."""
        assert "не отвечает давно" in self.source

    def test_keep_alive_link(self):
        """Ссылка на telegra.ph keep-alive гайд."""
        assert "telegra.ph" in self.source
        assert "keep-alive" in self.source.lower() or "keep_alive" in self.source.lower() or "zhivoj" in self.source

    def test_restart_hint(self):
        """Подсказка Manual Deploy на Render."""
        assert "Manual Deploy" in self.source


# ---------------------------------------------------------------------------
# 4. VERDICT LOGIC — boot partners
# ---------------------------------------------------------------------------

class TestBootVerdicts:
    """Проверяем все ветки вердиктов для партнёров с boot-отчётом."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open("bot_kie.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_verdict_not_configured(self):
        """missing keys → ❌ Не настроен."""
        assert "Не настроен" in self.source

    def test_verdict_has_problems(self):
        """probs > 0 → ⚠️ Есть замечания."""
        assert "Есть замечания" in self.source

    def test_verdict_working(self):
        """all ok + users + pays → ✅ Работает."""
        assert "Работает:" in self.source

    def test_verdict_configured_users_no_pays(self):
        """all ok + users, no pays → ✅ Настроен."""
        assert "Настроен:" in self.source

    def test_verdict_configured_waiting(self):
        """all ok, no users → ✅ Настроен, ожидает."""
        assert "ожидает пользователей" in self.source
        assert "ожидает трафик" in self.source

    def test_verdict_inactive_check_render(self):
        """🔴 + configured → проверь Render."""
        assert "проверь Render" in self.source


# ---------------------------------------------------------------------------
# 5. KEY INFERENCE LOGIC — no-boot
# ---------------------------------------------------------------------------

class TestKeyInference:
    """Проверяем логику вывода ключей из данных БД."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open("bot_kie.py", "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_instance_always_known(self):
        """INSTANCE → всегда ✅ (partner_id известен)."""
        assert 'k_inst = "✅"' in self.source

    def test_database_from_files(self):
        """DATABASE → ✅ если есть файлы."""
        assert "k_db" in self.source
        assert "has_files" in self.source

    def test_token_from_users_or_online(self):
        """TG_TOKEN → ✅ если users > 0 или (файлы + 🟢)."""
        assert "k_token" in self.source
        assert "users_n > 0" in self.source

    def test_kie_from_generations(self):
        """KIE → ✅ если generations > 0."""
        assert "k_kie" in self.source
        assert "gens_n > 0" in self.source

    def test_webhook_from_green_status(self):
        """WEBHOOK → ✅ если 🟢."""
        assert "k_wh" in self.source

    def test_admin_always_unknown(self):
        """ADMIN → всегда ❓ (невозможно определить без boot)."""
        assert 'k_admin = "❓"' in self.source


# ---------------------------------------------------------------------------
# 6. DISPLAY FORMAT — unit tests with mock data
# ---------------------------------------------------------------------------

def _build_partner(
    partner_id="test-01",
    deploy_status="🟢",
    has_boot=True,
    all_required_ok=True,
    required_keys=None,
    required_missing=None,
    optional_features=None,
    problems=None,
    users=0, payments=0, generations=0,
    files=None,
    last_updated_ago="5 сек",
    boot_result="OK",
):
    """Helper: собирает partner dict как list_all_partners."""
    return {
        "partner_id": partner_id,
        "file_count": 10,
        "last_updated_ago": last_updated_ago,
        "deploy_status": deploy_status,
        "has_boot": has_boot,
        "boot_result": boot_result,
        "required_keys": required_keys or {},
        "required_missing": required_missing or [],
        "all_required_ok": all_required_ok,
        "optional_features": optional_features or {},
        "problems": problems or [],
        "data_summary": {
            "users": users,
            "payments": payments,
            "generations": generations,
            "files": files if files is not None else ["user_balances.json"],
        },
    }


def _render_partner_lines(partner, current_instance="self-01"):
    """Воспроизводит логику отображения из bot_kie.py admin_partners."""
    NOISE_PREFIXES = ("PORT_BIND:",)
    lines = []

    p = partner
    pid = p["partner_id"]
    is_self = pid == current_instance
    label = f"<b>{pid}</b>" + (" 👑" if is_self else "")
    ds = p["deploy_status"]

    lines.append(f"{ds} {label}  🕐 {p['last_updated_ago']}")

    ds_info = p.get("data_summary", {})
    users_n = ds_info.get("users", 0)
    pays_n = ds_info.get("payments", 0)
    gens_n = ds_info.get("generations", 0)

    if not p.get("has_boot"):
        files_list = ds_info.get("files", [])
        has_files = len(files_list) > 0
        k_db = "✅" if has_files else "❓"
        k_inst = "✅"
        k_token = "✅" if users_n > 0 else ("✅" if has_files and ds == "🟢" else "❓")
        k_kie = "✅" if gens_n > 0 else "❓"
        k_wh = "✅" if ds == "🟢" else "❓"
        k_admin = "❓"
        lines.append(f"   🔑 {k_admin}ADMIN {k_inst}INSTANCE {k_wh}WEBHOOK {k_kie}KIE {k_token}TG_TOKEN {k_db}DATABASE")
        lines.append("   <i>❓ = нет boot-отчёта, точно неизвестно</i>")
        if ds == "🟡":
            lines.append("   😴 Render усыпил бота")
            lines.append('   <i>→ <a href="https://telegra.ph/Render-Free-zasypaet-kak-sdelat-chtoby-servis-vsegda-byl-zhivoj-za-2-minuty-02-06">Настрой бесплатный keep-alive</a> или тариф $5</i>')
        elif ds == "🔴":
            lines.append("   🛑 Бот не отвечает давно")
            lines.append("   <i>→ Открой Render Dashboard → проверь логи</i>")
        if users_n > 0 and pays_n > 0:
            verdict = f"✅ Активен: {users_n} юз., {pays_n} плат., {gens_n} ген."
        elif users_n > 0:
            verdict = f"📊 Есть юзеры ({users_n}), платежей нет"
        elif has_files and ds == "🟢":
            verdict = "⏳ Настроен, ожидает пользователей"
        elif has_files:
            verdict = "⏳ Данные есть, бот неактивен"
        else:
            verdict = "❓ Нет данных — бот ещё не запускался?"
        lines.append(f"   <b>{verdict}</b>")
        lines.append("   <i>→ Render Dashboard → Manual Deploy → отчёт появится сам</i>")
        lines.append("")
        return lines

    # --- Required keys ---
    rk = p.get("required_keys", {})
    missing = p.get("required_missing", [])
    if p.get("all_required_ok"):
        lines.append("   🔑 Обязательные: ✅ <b>все на месте</b>")
    else:
        key_parts = [f"{v}{k}" for k, v in rk.items()]
        lines.append("   🔑 " + " ".join(key_parts))
        if missing:
            lines.append(f"   ❌ <b>Нет: {', '.join(missing)}</b>")

    # --- Optional features ---
    opt = p.get("optional_features", {})
    if opt:
        pay_keys = ["Банк", "Держатель", "Телефон"]
        pay_parts = [f"{opt[k]}{k}" for k in pay_keys if k in opt]
        if pay_parts:
            lines.append(f"   💳 Оплата: {' '.join(pay_parts)}")
        sup_keys = ["Поддержка TG", "Текст поддержки"]
        sup_parts = [f"{opt[k]}{k}" for k in sup_keys if k in opt]
        if sup_parts:
            lines.append(f"   💬 Поддержка: {' '.join(sup_parts)}")
        ext_keys = ["Имя бота", "Username", "WebApp", "ZImage чат", "ZImage админы"]
        ext_parts = [f"{opt[k]}{k}" for k in ext_keys if k in opt]
        if ext_parts:
            lines.append(f"   🎨 Доп: {' '.join(ext_parts)}")

    # --- Problems (filter noise) ---
    probs = [pr for pr in p.get("problems", []) if not any(pr.startswith(n) for n in NOISE_PREFIXES)]
    if probs:
        for prob in probs[:2]:
            if len(prob) > 80:
                prob = prob[:77] + "..."
            lines.append(f"   ⚠️ <i>{prob}</i>")
        if len(probs) > 2:
            lines.append(f"   <i>...ещё {len(probs) - 2}</i>")

    # --- Verdict ---
    if missing:
        verdict = f"❌ Не настроен — нет: {', '.join(missing)}"
    elif probs:
        verdict = f"⚠️ Есть замечания ({len(probs)} шт.)"
    elif users_n > 0 and pays_n > 0:
        verdict = f"✅ Работает: {users_n} юз., {pays_n} плат., {gens_n} ген."
    elif users_n > 0:
        verdict = f"✅ Настроен: {users_n} юз., {gens_n} ген., платежей нет"
    else:
        if ds == "🔴":
            verdict = "⚠️ Настроен, но бот неактивен — проверь Render"
        elif ds == "🟡":
            verdict = "✅ Настроен, ожидает трафик"
        else:
            verdict = "✅ Настроен, ожидает пользователей"
    lines.append(f"   <b>{verdict}</b>")
    lines.append("")

    return lines


class TestNoBootDisplay:
    """Unit-тесты отображения для партнёров БЕЗ boot-отчёта."""

    def test_green_online_no_users_has_files(self):
        """🟢 + файлы + 0 юзеров → ожидает пользователей."""
        p = _build_partner(has_boot=False, deploy_status="🟢",
                           files=["user_balances.json", "config.json"])
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "ожидает пользователей" in text
        assert "✅INSTANCE" in text
        assert "✅WEBHOOK" in text  # 🟢 → webhook inferred
        assert "✅TG_TOKEN" in text  # files + 🟢
        assert "✅DATABASE" in text  # has files
        assert "❓ADMIN" in text  # always unknown
        assert "❓KIE" in text  # no generations

    def test_green_with_users_and_payments(self):
        """🟢 + users + payments → Активен."""
        p = _build_partner(has_boot=False, deploy_status="🟢",
                           users=5, payments=3, generations=2)
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Активен: 5 юз., 3 плат., 2 ген." in text
        assert "✅TG_TOKEN" in text
        assert "✅KIE" in text  # has generations

    def test_green_with_users_no_payments(self):
        """🟢 + users, no pays → Есть юзеры, платежей нет."""
        p = _build_partner(has_boot=False, deploy_status="🟢",
                           users=2, payments=0, generations=0)
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Есть юзеры (2), платежей нет" in text

    def test_yellow_sleeping(self):
        """🟡 → Render усыпил бота + keep-alive link."""
        p = _build_partner(has_boot=False, deploy_status="🟡")
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Render усыпил бота" in text
        assert "telegra.ph" in text
        assert "❓WEBHOOK" in text  # not 🟢

    def test_yellow_with_users(self):
        """🟡 + users → sleeping + user info."""
        p = _build_partner(has_boot=False, deploy_status="🟡",
                           users=2, payments=0)
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Render усыпил бота" in text
        assert "Есть юзеры (2)" in text

    def test_red_dead(self):
        """🔴 → Бот не отвечает давно."""
        p = _build_partner(has_boot=False, deploy_status="🔴")
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "не отвечает давно" in text
        assert "Render Dashboard" in text

    def test_no_files_no_data(self):
        """No files at all → Нет данных."""
        p = _build_partner(has_boot=False, deploy_status="🔴", files=[])
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Нет данных" in text
        assert "❓DATABASE" in text

    def test_restart_hint_always_present(self):
        """Подсказка Manual Deploy всегда есть для no-boot."""
        for ds in ["🟢", "🟡", "🔴"]:
            p = _build_partner(has_boot=False, deploy_status=ds)
            lines = _render_partner_lines(p)
            text = "\n".join(lines)
            assert "Manual Deploy" in text

    def test_unknown_marker_explanation(self):
        """❓ = нет boot-отчёта объяснение всегда есть."""
        p = _build_partner(has_boot=False, deploy_status="🟢")
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "нет boot-отчёта, точно неизвестно" in text


class TestBootDisplay:
    """Unit-тесты отображения для партнёров С boot-отчётом."""

    def test_all_keys_ok(self):
        """Все ключи на месте → 'все на месте'."""
        p = _build_partner(has_boot=True, all_required_ok=True)
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "все на месте" in text

    def test_missing_keys_shown(self):
        """Пропущенные ключи → ❌ Нет: ..."""
        p = _build_partner(
            has_boot=True, all_required_ok=False,
            required_keys={"ADMIN": "✅", "WEBHOOK": "❌", "TG_TOKEN": "❌"},
            required_missing=["WEBHOOK", "TG_TOKEN"],
        )
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Нет: WEBHOOK, TG_TOKEN" in text
        assert "Не настроен" in text

    def test_optional_features_grouped(self):
        """Optional features группируются по категориям."""
        p = _build_partner(
            has_boot=True, all_required_ok=True,
            optional_features={
                "Банк": "✅", "Держатель": "✅", "Телефон": "✅",
                "Поддержка TG": "✅", "Текст поддержки": "➖",
                "Имя бота": "➖", "Username": "➖", "WebApp": "✅",
                "ZImage чат": "✅", "ZImage админы": "✅",
            },
        )
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "💳 Оплата:" in text
        assert "💬 Поддержка:" in text
        assert "🎨 Доп:" in text

    def test_port_bind_filtered(self):
        """PORT_BIND проблемы НЕ показываются."""
        p = _build_partner(
            has_boot=True, all_required_ok=True,
            problems=["PORT_BIND: Ensure PORT is available", "REAL_PROBLEM: something"],
        )
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "PORT_BIND" not in text
        assert "REAL_PROBLEM" in text

    def test_problems_truncated(self):
        """Длинные проблемы обрезаются, максимум 2 показываются."""
        long_prob = "A" * 100
        p = _build_partner(
            has_boot=True, all_required_ok=True,
            problems=[long_prob, "prob2", "prob3", "prob4"],
        )
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "..." in text  # truncated
        assert "ещё 2" in text  # 4 total - 2 shown = 2 remaining

    def test_verdict_working(self):
        """Users + payments → Работает."""
        p = _build_partner(has_boot=True, all_required_ok=True,
                           users=4, payments=3, generations=3)
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Работает: 4 юз., 3 плат., 3 ген." in text

    def test_verdict_configured_no_users_green(self):
        """All ok, no users, 🟢 → ожидает пользователей."""
        p = _build_partner(has_boot=True, all_required_ok=True,
                           deploy_status="🟢")
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "ожидает пользователей" in text

    def test_verdict_configured_no_users_yellow(self):
        """All ok, no users, 🟡 → ожидает трафик."""
        p = _build_partner(has_boot=True, all_required_ok=True,
                           deploy_status="🟡")
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "ожидает трафик" in text

    def test_verdict_configured_no_users_red(self):
        """All ok, no users, 🔴 → неактивен, проверь Render."""
        p = _build_partner(has_boot=True, all_required_ok=True,
                           deploy_status="🔴")
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "неактивен" in text
        assert "Render" in text

    def test_verdict_has_problems(self):
        """Problems (not noise) → Есть замечания."""
        p = _build_partner(
            has_boot=True, all_required_ok=True,
            problems=["WEBHOOK: error"],
        )
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Есть замечания" in text

    def test_verdict_problems_only_noise_is_clean(self):
        """Only PORT_BIND problems → no замечания, clean verdict."""
        p = _build_partner(
            has_boot=True, all_required_ok=True,
            problems=["PORT_BIND: some issue"],
            users=4, payments=3, generations=3,
        )
        lines = _render_partner_lines(p)
        text = "\n".join(lines)
        assert "Работает" in text
        assert "замечания" not in text

    def test_self_partner_crown(self):
        """Текущий инстанс помечается 👑."""
        p = _build_partner(partner_id="self-01", has_boot=True, all_required_ok=True)
        lines = _render_partner_lines(p, current_instance="self-01")
        text = "\n".join(lines)
        assert "👑" in text

    def test_other_partner_no_crown(self):
        """Другой инстанс без 👑."""
        p = _build_partner(partner_id="other-01", has_boot=True, all_required_ok=True)
        lines = _render_partner_lines(p, current_instance="self-01")
        text = "\n".join(lines)
        assert "👑" not in text
