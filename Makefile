# Makefile для запуска тестов

.PHONY: install-deps lint test test-verbose test-menu test-callbacks smoke integrity e2e verify

# Установка зависимостей для тестов
install-deps:
	pip install -r requirements.txt

# Запуск тестов (краткий вывод)
verify-coverage:
	python -m scripts.verify_kie_coverage

test:
	TEST_MODE=1 DRY_RUN=1 ALLOW_REAL_GENERATION=0 BOT_MODE=passive PORT=8000 \
	ADMIN_ID=12345 DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
	KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
	PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
	TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=https://test.example.com \
	pytest -q tests/

# Запуск тестов (подробный вывод)
test-verbose:
	TEST_MODE=1 DRY_RUN=1 ALLOW_REAL_GENERATION=0 BOT_MODE=passive PORT=8000 \
	ADMIN_ID=12345 DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
	KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
	PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
	TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=https://test.example.com \
	pytest -v tests/

# Запуск конкретного теста
test-menu:
	TEST_MODE=1 DRY_RUN=1 ALLOW_REAL_GENERATION=0 BOT_MODE=passive PORT=8000 \
	ADMIN_ID=12345 DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
	KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
	PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
	TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=https://test.example.com \
	pytest -v tests/test_main_menu.py

test-callbacks:
	TEST_MODE=1 DRY_RUN=1 ALLOW_REAL_GENERATION=0 BOT_MODE=passive PORT=8000 \
	ADMIN_ID=12345 DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
	KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
	PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
	TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=https://test.example.com \
	pytest -v tests/test_callbacks_smoke.py

lint:
	ruff check app/main.py app/utils/healthcheck.py scripts/verify_project.py scripts/smoke_test_all_models.py
	ruff format --check app/main.py app/utils/healthcheck.py scripts/verify_project.py scripts/smoke_test_all_models.py

smoke:
	@bash -euo pipefail -c '\
		PORT=8080 BOT_MODE=webhook TEST_MODE=1 DRY_RUN=1 ADMIN_ID=12345 \
		DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
		KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
		PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
		TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=http://127.0.0.1:8080 \
		WEBHOOK_SECRET_PATH=test WEBHOOK_SECRET_TOKEN=smoke-secret \
		python scripts/smoke_server.py & \
		pid=$$!; \
		trap "kill $$pid" EXIT; \
		sleep 2; \
		curl -fsS http://127.0.0.1:8080/health; \
		curl -I -fsS http://127.0.0.1:8080/; \
		curl -fsS -X POST http://127.0.0.1:8080/webhook/test \
			-H "Content-Type: application/json" \
			-H "X-Telegram-Bot-Api-Secret-Token: smoke-secret" \
			-d "{\"update_id\":1,\"message\":{\"message_id\":1,\"date\":0,\"chat\":{\"id\":1,\"type\":\"private\"},\"text\":\"ping\"}}"; \
		'

integrity:
	TEST_MODE=1 DRY_RUN=1 BOT_MODE=webhook PORT=8080 \
	ADMIN_ID=12345 DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
	KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
	PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
	TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=https://test.example.com \
	python scripts/integrity_check.py

e2e:
	TEST_MODE=1 DRY_RUN=1 BOT_MODE=webhook PORT=8081 \
	ADMIN_ID=12345 DATABASE_URL=postgresql://test:test@localhost/test DB_MAXCONN=5 \
	KIE_API_KEY=test_api_key PAYMENT_BANK="Test Bank" PAYMENT_CARD_HOLDER="Test Holder" \
	PAYMENT_PHONE="+79991234567" SUPPORT_TELEGRAM="@test" SUPPORT_TEXT="Test support" \
	TELEGRAM_BOT_TOKEN=test_token_12345 WEBHOOK_BASE_URL=http://127.0.0.1:8081 \
	WEBHOOK_SECRET_PATH=test WEBHOOK_SECRET_TOKEN=smoke-secret \
	python scripts/e2e_smoke.py

verify: lint test smoke integrity e2e
