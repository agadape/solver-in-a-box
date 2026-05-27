.PHONY: install run-mock run-testnet test demo clean

PY := python3
VENV := .venv
ACTIVATE := . $(VENV)/bin/activate

install:
	$(PY) -m venv $(VENV)
	$(ACTIVATE) && pip install -U pip && pip install -e .

run-mock:
	@echo "Starting mock server + solver (mock mode)..."
	@$(ACTIVATE) && MODE=mock uvicorn mock_server.main:app --host 127.0.0.1 --port 8000 & \
		sleep 1 && MODE=mock $(PY) -m solver.main; \
		kill %1 2>/dev/null

run-testnet:
	@echo "Starting solver against order-dev.li.fi..."
	@$(ACTIVATE) && MODE=testnet $(PY) -m solver.main

test:
	$(ACTIVATE) && pytest -v

demo:
	@echo "Reproducible 60s demo run for video recording..."
	@$(ACTIVATE) && MODE=mock MOCK_INTERVAL_SECONDS=10 timeout 60 $(MAKE) run-mock || true

clean:
	rm -rf $(VENV) .pytest_cache __pycache__ */__pycache__ */*/__pycache__
