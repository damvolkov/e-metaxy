##### CONFIG #####
PROJECT    ?= e-metaxy
PACKAGE    ?= src/e_metaxy
MODULE     ?= e_metaxy
TEMPLATES  ?= ../e-templates/systems/core
COMMON_SRC ?= $(TEMPLATES)/common
TESTARGS    =
ARGS        = $(filter-out $@,$(MAKECMDGOALS))

RESET   := \033[0m
BOLD    := \033[1m
GREEN   := \033[0;32m
CYAN    := \033[0;36m
GRAY    := \033[0;90m

SHELL := bash
.DEFAULT_GOAL := help
MAKEFLAGS += --no-print-directory
export PYTHONPATH := $(CURDIR)/src
export E_CORE_SRC := $(abspath $(TEMPLATES))/src/e_core

##### TARGETS #####
.PHONY: help install sync lock core core-check common common-check lint type arch validate harden hooks test cov live check ci run unit clean

help:
	@printf "$(BOLD)$(CYAN)$(PROJECT)$(RESET) $(GRAY)· uv · mcp · granian · claude-agent-sdk — core/ops/adapters materialized from $(TEMPLATES)$(RESET)\n\n"
	@awk 'BEGIN{FS=":.*##"} /^[a-z][a-zA-Z0-9_-]*:.*##/{printf "  $(GREEN)%-12s$(RESET) $(GRAY)%s$(RESET)\n",$$1,$$2}' $(MAKEFILE_LIST)

# — env —
install: core common ## full setup: materialize shared assets + sync deps + git hooks
	@uv sync
	@uv run prek install
	@printf "$(GREEN)✓ ready$(RESET)\n"

sync: ## sync all deps (main + dev)
	@uv sync

lock: ## refresh uv lockfile
	@uv lock

# — shared —
core: ## materialize core/ + ops/ + adapters/ from e-templates systems/core (structural rewrite)
	@uv run python scripts/materialize.py

core-check: ## fail if the materialized core drifted from e-templates
	@uv run python scripts/materialize.py --check

common: ## materialize shared project files from systems/core/common
	@mkdir -p .github
	@cp $(COMMON_SRC)/prek.toml prek.toml
	@cp $(COMMON_SRC)/gitattributes .gitattributes
	@cp $(COMMON_SRC)/python-version .python-version
	@cp $(COMMON_SRC)/dependabot.yml .github/dependabot.yml
	@cp $(COMMON_SRC)/CODEOWNERS .github/CODEOWNERS

common-check: ## fail if the shared files drifted from systems/core/common
	@diff $(COMMON_SRC)/prek.toml prek.toml \
	 && diff $(COMMON_SRC)/gitattributes .gitattributes \
	 && diff $(COMMON_SRC)/python-version .python-version \
	 && diff $(COMMON_SRC)/dependabot.yml .github/dependabot.yml \
	 && diff $(COMMON_SRC)/CODEOWNERS .github/CODEOWNERS \
	 && printf "$(GREEN)✓ common in sync$(RESET)\n"

# — gates —
lint: ## ruff check + format
	@uv run ruff check --fix $(PACKAGE) src/core src/ops src/adapters scripts tests
	@uv run ruff format $(PACKAGE) src/core src/ops src/adapters scripts tests

type: ## ty type check
	@uv run ty check

arch: ## enforce import architecture (tach)
	@uv run tach check

validate: ## validate pyproject.toml against schema
	@uv run validate-pyproject pyproject.toml

harden: ## zizmor audit of GitHub Actions workflows
	@uv run zizmor --persona=regular .github/workflows

hooks: ## run all prek hooks on every file
	@uv run prek run --all-files

# — tests —
test: ## run tests [TESTARGS='-k expr']
	@uv run pytest tests $(TESTARGS) -n auto -q

cov: ## run tests with the coverage gate (100%)
	@uv run pytest tests --cov --cov-report=term-missing

live: ## drive the real Claude Code login on this host (spends subscription quota)
	@uv run pytest tests -m live -q -p no:randomly

# — aggregate —
check: lint type arch validate core-check common-check test ## fast local gate
ci: lint type arch validate harden core-check common-check cov ## every gate CI runs

# — run —
run: ## serve the bridge on loopback (granian)
	@uv run python -m $(MODULE) $(ARGS)

unit: ## install and start the systemd user unit
	@install -Dm644 ops/e-metaxy.service $(HOME)/.config/systemd/user/e-metaxy.service
	@systemctl --user daemon-reload
	@systemctl --user enable --now e-metaxy.service
	@systemctl --user --no-pager status e-metaxy.service | head -5

clean: ## remove caches and build artifacts
	@rm -rf .pytest_cache .ruff_cache .coverage dist build

%:
	@:
