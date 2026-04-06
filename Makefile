# =============================================================================
# SOC Copilot — Makefile
# Common commands for development, testing, and deployment
# =============================================================================

.PHONY: help setup install install-dev train test lint format run build clean

# Default target
help: ## Show this help message
	@echo "SOC Copilot — Available Commands"
	@echo "================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-15s %s\n", $$1, $$2}'

# ---- Setup & Installation ----

setup: ## Run the full automated setup
	python setup_project.py

install: ## Install production dependencies
	pip install -r requirements.txt
	pip install -e .

install-dev: ## Install with development dependencies
	pip install -r requirements-dev.txt
	pip install -e ".[dev]"

# ---- Model Training ----

train: ## Train all ML models (network-flow + text log)
	python scripts/train_models.py
	python scripts/train_text_log_model.py

train-network: ## Train network-flow models only
	python scripts/train_models.py

train-textlog: ## Train text log classifier only
	python scripts/train_text_log_model.py

# ---- Running ----

run: ## Launch the desktop UI
	python launch_ui.py

run-admin: ## Launch with admin elevation (for system log access)
	powershell -Command "Start-Process python -ArgumentList 'launch_ui.py' -Verb RunAs"

run-system-logs: ## Run system log ingestion (headless)
	python run_system_logs.py

# ---- Testing ----

test: ## Run all tests
	python -m pytest tests/ -v

test-unit: ## Run unit tests only
	python -m pytest tests/unit/ -v

test-integration: ## Run integration tests only
	python -m pytest tests/integration/ -v

test-coverage: ## Run tests with HTML coverage report
	python -m pytest tests/ --cov=soc_copilot --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ---- Code Quality ----

lint: ## Run all code quality checks
	ruff src/ tests/
	mypy src/

format: ## Format code with black
	black src/ tests/ --line-length 100

check: ## Verify system requirements
	python check_requirements.py

# ---- Build & Distribution ----

build: ## Build standalone executable with PyInstaller
	python scripts/build_exe.py

# ---- Cleanup ----

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info
	rm -rf __pycache__ src/**/__pycache__ tests/**/__pycache__
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
	rm -rf *.pyc *.pyo
	@echo "Cleaned all build artifacts."
