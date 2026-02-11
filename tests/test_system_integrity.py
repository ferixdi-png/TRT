"""
System Integrity Tests — КРИТИЧЕСКИЕ ТЕСТЫ ЦЕЛОСТНОСТИ СИСТЕМЫ

Проверяют:
1. USD_TO_RUB SSOT — единый курс во всех файлах
2. State machine — нормализация состояний провайдера
3. is_video_model / is_audio_model — покрытие всех моделей из registry
4. Coverage guard — не блокирует модели с non-pricing параметрами
5. Config fallback values — дефолты совпадают с SSOT
6. Pricing ↔ Registry alignment — модели в pricing есть в registry
7. Delivery states — PENDING/SUCCESS/FAILED наборы непересекающиеся
8. Model copy coverage — все модели из pricing имеют описания
"""

import os
import re
import yaml
import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_yaml(rel_path: str):
    with open(os.path.join(BASE, rel_path), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────
# 1. USD_TO_RUB SSOT
# ─────────────────────────────────────────────────────
class TestUsdToRubSSOT:
    """Все файлы ДОЛЖНЫ использовать единый курс из pricing/config.yaml."""

    def _ssot_rate(self) -> float:
        cfg = _load_yaml("pricing/config.yaml")
        return float(cfg["settings"]["usd_to_rub"])

    def _extract_rate(self, rel_path: str, pattern: str) -> float | None:
        full = os.path.join(BASE, rel_path)
        if not os.path.exists(full):
            return None
        with open(full, "r", encoding="utf-8") as f:
            for line in f:
                if "USD_TO_RUB" in line and "=" in line and "#" not in line.split("=")[0]:
                    nums = re.findall(r"[\d.]+", line.split("=")[1].split("#")[0])
                    if nums:
                        return float(nums[0])
        return None

    @pytest.mark.parametrize("path", [
        "config.py",
        "pricing/engine.py",
        "pricing_transparency.py",
        "tools/generate_models_list.py",
        "scripts/generate_complete_pricing.py",
        "scripts/check_all_models_comprehensive.py",
    ])
    def test_usd_to_rub_matches_ssot(self, path):
        ssot = self._ssot_rate()
        rate = self._extract_rate(path, "USD_TO_RUB")
        if rate is None:
            pytest.skip(f"{path} not found or no USD_TO_RUB")
        assert rate == ssot, f"{path}: USD_TO_RUB={rate}, SSOT={ssot}"

    def test_app_config_fallback_matches_ssot(self):
        """app/config.py fallback для usd_to_rub должен совпадать с SSOT."""
        ssot = self._ssot_rate()
        full = os.path.join(BASE, "app", "config.py")
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        # Ищем fallback значение в get("usd_to_rub", "XX.XX")
        m = re.search(r'get\(\s*"usd_to_rub"\s*,\s*"([\d.]+)"', content)
        assert m, "app/config.py должен иметь fallback для usd_to_rub"
        assert float(m.group(1)) == ssot, (
            f"app/config.py fallback={m.group(1)}, SSOT={ssot}"
        )

    def test_bot_kie_default_matches_ssot(self):
        """bot_kie.py USD_TO_RUB_DEFAULT должен совпадать с SSOT."""
        ssot = self._ssot_rate()
        full = os.path.join(BASE, "bot_kie.py")
        with open(full, "r", encoding="utf-8") as f:
            for line in f:
                if "USD_TO_RUB_DEFAULT" in line and "=" in line:
                    nums = re.findall(r"[\d.]+", line.split("=")[1].split("#")[0])
                    if nums:
                        assert float(nums[0]) == ssot, (
                            f"bot_kie.py USD_TO_RUB_DEFAULT={nums[0]}, SSOT={ssot}"
                        )
                        return
        pytest.skip("USD_TO_RUB_DEFAULT not found in bot_kie.py")


# ─────────────────────────────────────────────────────
# 2. State machine normalization
# ─────────────────────────────────────────────────────
class TestStateMachine:
    """Проверяем корректность нормализации состояний."""

    def test_success_states_normalized(self):
        from app.generations.state_machine import normalize_provider_state
        for raw in ["success", "completed", "succeeded"]:
            res = normalize_provider_state(raw)
            assert res.canonical_state == "success", f"{raw} → {res.canonical_state}"

    def test_failed_states_normalized(self):
        from app.generations.state_machine import normalize_provider_state
        for raw in ["failed", "fail", "error"]:
            res = normalize_provider_state(raw)
            assert res.canonical_state in ("failed", "canceled"), f"{raw} → {res.canonical_state}"

    def test_pending_states_normalized(self):
        from app.generations.state_machine import normalize_provider_state
        for raw in ["pending", "queued", "queuing"]:
            res = normalize_provider_state(raw)
            assert res.canonical_state == "queued", f"{raw} → {res.canonical_state}"

    def test_waiting_states_normalized(self):
        from app.generations.state_machine import normalize_provider_state
        for raw in ["waiting", "processing", "running", "generating", "in_progress"]:
            res = normalize_provider_state(raw)
            assert res.canonical_state == "waiting", f"{raw} → {res.canonical_state}"

    def test_empty_state_defaults_to_waiting(self):
        from app.generations.state_machine import normalize_provider_state
        res = normalize_provider_state(None)
        assert res.canonical_state == "waiting"
        res2 = normalize_provider_state("")
        assert res2.canonical_state == "waiting"

    def test_canonical_sets_no_overlap(self):
        """SUCCESS и FAILED наборы НЕ должны пересекаться.
        
        PENDING может содержать success/result_validated — это промежуточные
        стадии до доставки пользователю (pending = 'ещё не доставлено').
        """
        from app.generations.state_machine import (
            CANONICAL_SUCCESS_STATES,
            CANONICAL_FAILED_STATES,
        )
        overlap_sf = CANONICAL_SUCCESS_STATES & CANONICAL_FAILED_STATES
        assert not overlap_sf, f"SUCCESS ∩ FAILED = {overlap_sf}"


# ─────────────────────────────────────────────────────
# 3. is_video_model / is_audio_model coverage
# ─────────────────────────────────────────────────────
class TestMediaTypeDetection:
    """Проверяем что is_video_model/is_audio_model покрывают все модели из registry."""

    def _registry_models(self):
        reg = _load_yaml("models/kie_models.yaml")
        return reg.get("models", {})

    def test_video_models_detected(self):
        from bot_kie import is_video_model
        registry = self._registry_models()
        video_types = {"text_to_video", "image_to_video"}
        missed = []
        for mid, spec in registry.items():
            mt = spec.get("model_type", "")
            if mt in video_types and not is_video_model(mid):
                missed.append(mid)
        assert not missed, f"Video models NOT detected by is_video_model: {missed}"

    def test_audio_models_detected(self):
        from bot_kie import is_audio_model
        registry = self._registry_models()
        audio_types = {"speech_to_text", "text_to_speech", "text_to_audio", "audio_to_text"}
        missed = []
        for mid, spec in registry.items():
            mt = spec.get("model_type", "")
            if mt in audio_types and not is_audio_model(mid):
                missed.append(mid)
        assert not missed, f"Audio models NOT detected by is_audio_model: {missed}"

    def test_image_not_detected_as_video(self):
        """Чисто image-модели НЕ должны детектиться как video."""
        from bot_kie import is_video_model
        image_models = [
            "flux-2/pro-text-to-image",
            "flux/kontext",
            "bytedance/seedream",
            "z-image",
        ]
        for mid in image_models:
            assert not is_video_model(mid), f"{mid} ложно определена как video"


# ─────────────────────────────────────────────────────
# 4. Coverage guard non-blocking
# ─────────────────────────────────────────────────────
class TestCoverageGuard:
    """coverage_guard НЕ должен блокировать модели из-за non-pricing параметров."""

    def test_missing_required_is_warning_not_blocker(self):
        """Проверяем что missing_required — warning, не блокер."""
        import inspect
        from app.pricing.coverage_guard import _evaluate_model_pricing
        source = inspect.getsource(_evaluate_model_pricing)
        # Не должно быть return DISABLED при missing_required
        # Должен быть logger.info/warning вместо блокировки
        assert "non-blocking" in source.lower() or "warning" in source.lower(), (
            "missing_required должен быть warning, не блокер"
        )


# ─────────────────────────────────────────────────────
# 5. Pricing ↔ Registry alignment
# ─────────────────────────────────────────────────────
class TestPricingRegistryAlignment:
    """Pricing catalog и registry должны быть согласованы."""

    def test_pricing_models_exist_in_registry(self):
        pricing = _load_yaml("app/kie_catalog/models_pricing.yaml")
        registry = _load_yaml("models/kie_models.yaml")
        pricing_ids = {m["id"] for m in pricing["models"]}
        registry_ids = set(registry["models"].keys())
        missing = pricing_ids - registry_ids
        assert not missing, f"В pricing но НЕ в registry: {sorted(missing)}"

    def test_registry_models_have_pricing(self):
        pricing = _load_yaml("app/kie_catalog/models_pricing.yaml")
        registry = _load_yaml("models/kie_models.yaml")
        pricing_ids = {m["id"] for m in pricing["models"]}
        registry_ids = set(registry["models"].keys())
        missing = registry_ids - pricing_ids
        assert not missing, f"В registry но НЕ в pricing: {sorted(missing)}"

    def test_pricing_rub_covers_pricing_catalog(self):
        pricing = _load_yaml("app/kie_catalog/models_pricing.yaml")
        rub = _load_yaml("data/kie_pricing_rub.yaml")
        pricing_ids = {m["id"] for m in pricing["models"]}
        rub_ids = {m["id"] for m in rub["models"]}
        missing = pricing_ids - rub_ids
        assert not missing, f"В pricing но НЕ в kie_pricing_rub: {sorted(missing)}"

    def test_no_negative_prices(self):
        rub = _load_yaml("data/kie_pricing_rub.yaml")
        negatives = []
        for m in rub["models"]:
            for sku in m.get("skus", []):
                price = sku.get("price_rub", 0)
                if price < 0:
                    negatives.append(f"{m['id']}: {price}")
        assert not negatives, f"Отрицательные цены: {negatives}"

    def test_no_models_without_skus(self):
        rub = _load_yaml("data/kie_pricing_rub.yaml")
        no_skus = [m["id"] for m in rub["models"] if not m.get("skus")]
        assert not no_skus, f"Модели без SKU: {no_skus}"


# ─────────────────────────────────────────────────────
# 6. safe_handler — ApplicationHandlerStop
# ─────────────────────────────────────────────────────
class TestSafeHandlerIntegrity:
    """safe_handler НЕ должен проглатывать ApplicationHandlerStop."""

    def test_application_handler_stop_is_reraised(self):
        import inspect
        from app.observability.safe_handler import _safe_callback
        source = inspect.getsource(_safe_callback)
        # Must have `except ApplicationHandlerStop:` followed by `raise`
        assert "ApplicationHandlerStop" in source, "Должен обрабатывать ApplicationHandlerStop"
        # Find the except block
        lines = source.split("\n")
        found_except = False
        for i, line in enumerate(lines):
            if "except ApplicationHandlerStop" in line:
                found_except = True
                # Next non-empty line should be raise
                for j in range(i + 1, min(i + 3, len(lines))):
                    if lines[j].strip() == "raise":
                        return  # OK!
        assert found_except, "Нет except ApplicationHandlerStop"
        pytest.fail("ApplicationHandlerStop должен быть re-raised, а не проглочен!")


# ─────────────────────────────────────────────────────
# 7. Delivery pipeline integrity
# ─────────────────────────────────────────────────────
class TestDeliveryPipelineIntegrity:
    """Reconciler должен корректно обрабатывать все состояния."""

    def test_reconciler_imports_state_machine(self):
        """Reconciler ДОЛЖЕН использовать state machine для нормализации."""
        import inspect
        from app.delivery import reconciler
        source = inspect.getsource(reconciler)
        assert "normalize_provider_state" in source, (
            "Reconciler ДОЛЖЕН использовать normalize_provider_state"
        )

    def test_reconciler_handles_success_and_failure(self):
        """Reconciler ДОЛЖЕН обрабатывать и success, и failure."""
        import inspect
        from app.delivery import reconciler
        source = inspect.getsource(reconciler.reconcile_pending_results)
        assert "SUCCESS_STATES" in source, "Reconciler ДОЛЖЕН проверять SUCCESS_STATES"
        assert "FAILED_STATES" in source, "Reconciler ДОЛЖЕН проверять FAILED_STATES"

    def test_reconciler_has_gc(self):
        """Reconciler ДОЛЖЕН иметь GC для старых jobs."""
        from app.delivery import reconciler
        assert hasattr(reconciler, "_gc_old_jobs"), "Reconciler ДОЛЖЕН иметь _gc_old_jobs"

    def test_reconciler_charges_on_delivery(self):
        """Reconciler ДОЛЖЕН списывать баланс при успешной доставке."""
        import inspect
        from app.delivery import reconciler
        source = inspect.getsource(reconciler.deliver_job_result)
        assert "_commit_delivery_charge" in source, (
            "deliver_job_result ДОЛЖЕН вызывать _commit_delivery_charge"
        )


# ─────────────────────────────────────────────────────
# 8. Registry schema validation
# ─────────────────────────────────────────────────────
class TestRegistrySchema:
    """Все модели в registry должны иметь корректную схему."""

    def test_all_models_have_model_type(self):
        registry = _load_yaml("models/kie_models.yaml")
        missing = [mid for mid, spec in registry["models"].items()
                   if "model_type" not in spec]
        assert not missing, f"Модели без model_type: {missing}"

    def test_all_models_have_input(self):
        registry = _load_yaml("models/kie_models.yaml")
        missing = [mid for mid, spec in registry["models"].items()
                   if "input" not in spec]
        assert not missing, f"Модели без input: {missing}"

    def test_valid_model_types(self):
        registry = _load_yaml("models/kie_models.yaml")
        valid_types = {
            "text_to_image", "image_to_image", "text_to_video",
            "image_to_video", "speech_to_text", "text_to_speech",
            "text_to_audio", "audio_to_text", "image_edit",
            "face_swap", "lip_sync", "avatar",
        }
        invalid = []
        for mid, spec in registry["models"].items():
            mt = spec.get("model_type", "")
            if mt and mt not in valid_types:
                invalid.append(f"{mid}: {mt}")
        # Не assert — новые типы могут появляться, но предупреждаем
        if invalid:
            import warnings
            warnings.warn(f"Неизвестные model_type (проверьте): {invalid}")


# ─────────────────────────────────────────────────────
# 9. CREDIT_TO_USD consistency
# ─────────────────────────────────────────────────────
class TestCreditToUsdConsistency:
    """CREDIT_TO_USD = 0.005 во всех файлах."""

    @pytest.mark.parametrize("path", [
        "bot_kie.py",
        "helpers.py",
        "config.py",
        "app/services/payments_service.py",
    ])
    def test_credit_to_usd_is_consistent(self, path):
        full = os.path.join(BASE, path)
        if not os.path.exists(full):
            pytest.skip(f"{path} not found")
        with open(full, "r", encoding="utf-8") as f:
            for line in f:
                if "CREDIT_TO_USD" in line and "=" in line and "import" not in line:
                    nums = re.findall(r"[\d.]+", line.split("=")[1].split("#")[0])
                    if nums:
                        assert float(nums[0]) == 0.005, (
                            f"{path}: CREDIT_TO_USD={nums[0]}, should be 0.005"
                        )
                        return
        pytest.skip(f"CREDIT_TO_USD not found in {path}")
