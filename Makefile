.PHONY: verify test clean install firebreak smoke-render deploy-check syntax truth-gate test-lock verify-truth

# TRUTH GATE: Полная валидация архитектурного контракта
truth-gate:
	@echo "🏛️ TRUTH GATE: Running architecture contract validation..."
	@echo ""
	@echo "1️⃣ verify_truth.py (architecture invariants)..."
	python3 verify_truth.py
	@echo ""
	@echo "2️⃣ Unit tests (lock mechanism)..."
	python3 -m pytest tests/test_render_singleton_lock.py -v
	@echo ""
	@echo "3️⃣ Syntax check..."
	python3 -m py_compile main_render.py
	python3 -m py_compile render_singleton_lock.py
	@echo ""
	@echo "✅ ALL TRUTH GATES PASSED"

# verify_truth standalone
verify-truth:
	@echo "🔍 Running verify_truth.py..."
	@python3 verify_truth.py

# test-lock standalone
test-lock:
	@echo "🧪 Running lock mechanism tests..."
	@python3 -m pytest tests/test_render_singleton_lock.py -v

# FIREBREAK: Полная проверка перед деплоем (критично!)
firebreak: truth-gate
	@echo ""
	@echo "2️⃣ Smoke test (локально)..."
	python3 smoke_test.py || true
	@echo ""
	@echo "✅ FIREBREAK: Все проверки пройдены!"

# Smoke test на Render
smoke-render:
	@echo "🧪 Smoke test на Render..."
	python3 smoke_test.py --url https://five656.onrender.com

# Smoke test для button instrumentation
smoke-buttons:
	@echo "🧪 Smoke test: Button Instrumentation..."
	python3 scripts/smoke_buttons_instrumentation.py

# Smoke test для webhook production readiness (P0)
smoke-webhook:
	@echo "🧪 Smoke test: Webhook Production Readiness..."
	python3 scripts/smoke_webhook.py

# Render log watcher (last 30 minutes)
render-logs:
	@echo "📊 Fetching Render logs (last 30 minutes)..."
	python scripts/render_watch.py --minutes 30

# Render log watcher (last 10 minutes)
render-logs-10:
	@echo "📊 Fetching Render logs (last 10 minutes)..."
	python scripts/render_watch.py --minutes 10

# Smoke test (alias для удобства)
smoke: smoke-webhook
	@echo "✅ Smoke tests complete"

# Проверка логов Render после деплоя (ждем 2 минуты)
deploy-check:
	@echo "🔍 Проверка Render логов..."
	@echo "⏳ Ждем 2 минуты для стабилизации деплоя..."
	@sleep 120
	python3 check_render_logs.py --minutes 10

# Быстрая проверка синтаксиса
syntax:
	@python3 -m py_compile render_singleton_lock.py
	@python3 -m py_compile app/utils/update_queue.py
	@python3 -m py_compile smoke_test.py
	@python3 -m py_compile check_render_logs.py
	@echo "✅ Синтаксис корректен"

# Verify critical functionality before deploy
verify:
	@echo "🔍 Running critical state machine verification..."
	pytest tests/test_state_machine_verify.py -v --tb=short
	@echo "✅ State machine verification complete"

# Install dependencies
install:
	pip install -r requirements.txt

# Clean Python artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
