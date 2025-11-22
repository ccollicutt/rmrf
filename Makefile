# Makefile for rmrf (Public Version)

# Variables
PYTHON := .venv/bin/python
UV := uv pip
SHELL := /bin/bash

.PHONY: help default setup-venv install install-dev test lint format type-check security check quality pre-commit clean

# Default goal
.DEFAULT_GOAL := help

help: ## Show available targets
	@echo ""
	@echo "rmrf - Safety-critical deletion utility"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "; category = ""} \
		/^## Category:/ { category = substr($$0, 14); next } \
		/^[a-zA-Z_-]+:.*?## / { \
			if (category != last_category) { \
				if (last_category != "") print ""; \
				print "\033[1m" category "\033[0m"; \
				last_category = category; \
			} \
			printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2 \
		}' $(MAKEFILE_LIST)
	@echo ""

## Category: Setup & Installation

setup-system-deps: ## Install system dependencies (make, binutils) - requires sudo
	@echo "Installing system dependencies..."
	@if command -v apt-get &>/dev/null; then \
		sudo apt-get update -qq && sudo apt-get install -y make binutils; \
		echo "System dependencies installed (make, binutils)"; \
	elif command -v yum &>/dev/null; then \
		sudo yum install -y make binutils; \
		echo "System dependencies installed (make, binutils)"; \
	elif command -v brew &>/dev/null; then \
		brew install make binutils; \
		echo "System dependencies installed (make, binutils)"; \
	else \
		echo "ERROR: Package manager not found (apt-get, yum, or brew)"; \
		echo "Please install 'make' and 'binutils' manually"; \
		exit 1; \
	fi

setup-venv: ## Create virtual environment with uv
	uv venv .venv

install: ## Install package in editable mode
	$(UV) install -e .

install-dev: ## Install package with dev dependencies
	$(UV) install -e ".[dev]"

install-pyinstaller: ## Install PyInstaller for binary builds
	$(UV) install pyinstaller

dev-setup: setup-venv install-dev ## Complete dev environment setup
	@echo "Development environment ready!"
	@echo "Run 'source .venv/bin/activate' to activate"

dev-setup-full: setup-system-deps dev-setup install-pyinstaller ## Full setup including system deps and PyInstaller
	@echo ""
	@echo "Full development environment ready!"
	@echo ""
	@echo "Installed:"
	@echo "  - System: make, binutils"
	@echo "  - Python: rmrf + dev dependencies"
	@echo "  - PyInstaller: for building binaries"
	@echo ""
	@echo "Run 'source .venv/bin/activate' to activate"
	@echo ""

quickstart: dev-setup ## Quick start for new developers
	@echo ""
	@echo "Welcome to rmrf development!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. source .venv/bin/activate"
	@echo "  2. make test                    # Run tests"
	@echo "  3. Read README.md               # Understand the project"
	@echo ""
	@echo "To build binaries, run:"
	@echo "  make dev-setup-full             # Install PyInstaller + system deps"
	@echo "  make build-binary               # Build the binary"
	@echo ""

## Category: Testing

test: ## Run all tests with pytest
	PYTHONPATH=src $(PYTHON) -m pytest tests/ -v

test-unit: ## Run only unit tests
	PYTHONPATH=src $(PYTHON) -m pytest tests/unit/ -v

test-integration: ## Run only integration tests
	PYTHONPATH=src $(PYTHON) -m pytest tests/integration/ -v

test-coverage: ## Run tests with coverage report
	PYTHONPATH=src $(PYTHON) -m pytest tests/ -v --cov=src/rmrf --cov-report=html --cov-report=term

## Category: Code Quality

lint: ## Run ruff linter
	$(PYTHON) -m ruff check src/ tests/

format: ## Format code with ruff
	$(PYTHON) -m ruff format src/ tests/
	$(PYTHON) -m ruff check --fix src/ tests/

type-check: ## Run mypy type checker
	PYTHONPATH=src $(PYTHON) -m mypy src/rmrf

security: ## Run bandit security scanner
	$(PYTHON) -m bandit -c pyproject.toml -r src/

check: lint type-check security ## Run all static checks (lint + type-check + security)

quality: check ## Run all quality checks
	@echo "All quality checks passed!"

pre-commit: format lint type-check security test ## Run all checks before committing
	@echo "All pre-commit checks passed!"

## Category: Utilities

clean: ## Clean Python cache files and build artifacts
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +
	find . -type d -name ".ruff_cache" -exec rm -r {} +
	find . -type d -name ".mypy_cache" -exec rm -r {} +
	find . -type d -name "htmlcov" -exec rm -r {} +
	find . -type f -name ".coverage" -delete

## Category: Binary Build

check-build-deps: ## Check if binary build dependencies are installed
	@echo "Checking build dependencies..."
	@MISSING=""; \
	if ! command -v make >/dev/null 2>&1; then MISSING="$$MISSING make"; fi; \
	if ! command -v objdump >/dev/null 2>&1; then MISSING="$$MISSING binutils"; fi; \
	if ! $(PYTHON) -c "import PyInstaller" 2>/dev/null; then MISSING="$$MISSING pyinstaller"; fi; \
	if [ -n "$$MISSING" ]; then \
		echo "Missing dependencies:$$MISSING"; \
		echo ""; \
		echo "Install with: make dev-setup-full"; \
		echo "Or individually:"; \
		echo "  - System deps: make setup-system-deps"; \
		echo "  - PyInstaller: make install-pyinstaller"; \
		exit 1; \
	fi; \
	echo "All build dependencies present"

build-binary: check-build-deps ## Build standalone binary with PyInstaller
	@echo "Building rmrf binary..."
	@mkdir -p bin
	@rm -rf pyinstaller-build
	PYTHONPATH=src pyinstaller \
		--clean \
		--onefile \
		--name rmrf \
		--workpath pyinstaller-build \
		--distpath bin \
		--hidden-import yaml \
		--hidden-import click \
		--hidden-import pydantic \
		--hidden-import requests \
		--add-data "src/rmrf/cli/commands/about.txt:rmrf/cli/commands" \
		--add-data "config:config" \
		src/rmrf_main.py
	@echo "Binary built successfully: bin/rmrf"
	@echo "Testing binary..."
	@./bin/rmrf --version

build-binary-debug: ## Build binary with debug output
	@echo "Building rmrf binary with debug output..."
	@mkdir -p bin
	@rm -rf pyinstaller-build
	PYTHONPATH=src pyinstaller \
		--clean \
		--onefile \
		--name rmrf \
		--workpath pyinstaller-build \
		--distpath bin \
		--debug all \
		--hidden-import yaml \
		--hidden-import click \
		--hidden-import pydantic \
		--hidden-import requests \
		--add-data "src/rmrf/cli/commands/about.txt:rmrf/cli/commands" \
		--add-data "config:config" \
		src/rmrf_main.py
	@echo "Debug binary built: bin/rmrf"

clean-binary: ## Remove binary build artifacts
	@echo "Cleaning binary build artifacts..."
	@rm -rf bin/ pyinstaller-build/
	@echo "Done!"

## Category: Release

release: ## Tag and push current version
	@echo "=========================================="
	@echo "           Release Workflow"
	@echo "=========================================="
	@version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	echo ""; \
	echo "Current version: $$version"; \
	echo ""; \
	echo "=========================================="; \
	echo "  Release version: v$$version"; \
	echo "=========================================="; \
	echo ""; \
	echo "This will:"; \
	echo "  1. Create git tag: v$$version"; \
	echo "  2. Push to origin main"; \
	echo "  3. Push tag (triggers GitHub release)"; \
	echo ""; \
	read -p "Proceed with release? [y/N]: " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
		echo "Release cancelled."; \
		exit 1; \
	fi; \
	echo ""; \
	echo "Creating release..."; \
	git tag -a "v$$version" -m "Release v$$version"; \
	git push origin main; \
	git push origin "v$$version"; \
	echo ""; \
	echo "✓ Released v$$version"; \
	echo "✓ GitHub Actions will build binary and create release"
