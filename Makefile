.PHONY: verify test clean install

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
