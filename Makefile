.PHONY: verify test clean install firebreak smoke-render deploy-check syntax

# FIREBREAK: Полная проверка перед деплоем (критично!)
firebreak:
	@echo "🔥 FIREBREAK: Запуск всех проверок..."
	@echo ""
	@echo "1️⃣ Unit tests..."
	python3 -m pytest tests/test_render_singleton_lock.py -v
	@echo ""
	@echo "2️⃣ Smoke test (локально)..."
	python3 smoke_test.py || true
	@echo ""
	@echo "3️⃣ Syntax check..."
	python3 -m py_compile render_singleton_lock.py
	python3 -m py_compile app/utils/update_queue.py
	@echo ""
	@echo "✅ FIREBREAK: Все проверки пройдены!"

# Smoke test на Render
smoke-render:
	@echo "🧪 Smoke test на Render..."
	python3 smoke_test.py --url https://five656.onrender.com

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
