##### CONFIG #####
PROJECT  ?= e-organon
PACKAGE  ?= src/e_organon
MODULE   ?= e_organon
PORT     ?= 8000
COMPOSE  ?= compose.yml
TESTARGS  ?= -m "not slow and not integration"   ## real-service tests leave the gate: make test TESTARGS="-m slow", make integration
ARGS      = $(filter-out $@,$(MAKECMDGOALS))

RESET   := \033[0m
BOLD    := \033[1m
GREEN   := \033[0;32m
CYAN    := \033[0;36m
GRAY    := \033[0;90m
RED     := \033[0;31m

SHELL := bash
.DEFAULT_GOAL := help
MAKEFLAGS += --no-print-directory
export PYTHONPATH := $(CURDIR)/src

##### TARGETS #####
.PHONY: help install sync lock lint type arch validate harden hooks test integration cov stress docs docs-build check ci run up down build logs release ci-vars clean

help:
	@printf "$(BOLD)$(CYAN)$(PROJECT)$(RESET) $(GRAY)· uv · ruff · ty · tach · pytest · zensical · docker$(RESET)\n\n"
	@awk 'BEGIN{FS=":.*##"} /^[a-z][a-zA-Z0-9_-]*:.*##/{printf "  $(GREEN)%-12s$(RESET) $(GRAY)%s$(RESET)\n",$$1,$$2}' $(MAKEFILE_LIST)

# — env —
install: ## full setup: materialize shared assets + sync deps + git hooks
	@uv sync
	@uv run prek install
	@printf "$(GREEN)✓ ready$(RESET)\n"

sync: ## sync all deps (main + dev)
	@uv sync

lock: ## refresh uv lockfile (against the current materialized)
	@uv lock

# — gates —
lint: ## ruff check + format
	@uv run ruff check --fix $(PACKAGE) src/infra src/ops src/ports src/providers src/engines src/processors scripts tests
	@uv run ruff format $(PACKAGE) src/infra src/ops src/ports src/providers src/engines src/processors scripts tests

type: ## ty type check
	@uv run ty check

arch: ## enforce import architecture (tach)
	@uv run tach check

validate: ## validate pyproject.toml against schema
	@uv run validate-pyproject pyproject.toml

harden: ## zizmor audit of GitHub Actions workflows (templates assemble them at generation)
	@test -d .github/workflows && uv run zizmor --persona=regular .github/workflows || echo "no workflows assembled: e-taxis writes them"

hooks: ## run all prek hooks on every file (ruff, ty, tach, zizmor, gitleaks)
	@uv run prek run --all-files

# — tests —
test: ## run tests [TESTARGS='-k expr']
	@uv run pytest tests $(TESTARGS) -n auto -q

integration: ## the tests that need a real service (Postgres at POSTGRES_DSN, redis at REDIS_URL); skipped when none answers
	@uv run pytest tests -m integration -q

cov: ## run tests with coverage gate (fail under 100%), real-service tests out like the default run
	@uv run pytest tests $(TESTARGS) --cov --cov-report=term-missing

stress: ## soak stress-marked tests for ARGS seconds (pytest-stress)
	@uv run pytest tests -m stress -q -p no:randomly --seconds $(or $(ARGS),30)

# — docs —
docs: ## serve docs site live at :8000
	@uv run zensical serve

docs-build: ## strict docs build to site/
	@uv run zensical build --strict

# — aggregate —
check: lint type arch validate test ## fast local gate: lint + type + arch + validate + drift + test
ci: lint type arch validate harden docs-build cov ## full pipeline: every gate CI runs, in one command

# — release —
release: ## cut a GitHub release via the release workflow [args: patch|minor|major]
	@gh workflow run release.yml -f bump=$(or $(ARGS),patch)
	@sleep 5
	@gh run watch --exit-status $$(gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')

ci-vars: ## list optional CI/CD gates (all inert by default) and their defaults
	@printf "$(BOLD)optional CI/CD gates$(RESET) $(GRAY)— enable: gh variable set NAME --body true · manifest: .github/ci.vars.example$(RESET)\n\n"
	@grep -E '^[A-Z][A-Z0-9_]*=' .github/ci.vars.example

# — run —
run: ## run app locally [args: forwarded]
	@uv run python -m $(MODULE) $(ARGS)

up: ## docker compose up (materializes into the build context first) [args: services]
	@docker compose -f $(COMPOSE) up -d $(ARGS)
	@printf "$(GREEN)✓ up$(RESET) $(GRAY)http://localhost:$(PORT)$(RESET)\n"

down: ## docker compose down
	@docker compose -f $(COMPOSE) down

build: ## docker image build [args: services]
	@docker compose -f $(COMPOSE) build $(ARGS)

logs: ## tail docker logs [args: service]
	@docker compose -f $(COMPOSE) logs -f $(ARGS)

clean: ## remove caches + build artifacts + materialized
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} + 2>/dev/null || true
	@rm -rf dist build *.egg-info .coverage .coverage.* .ty_cache site
	@printf "$(GREEN)✓ clean$(RESET)\n"

%:
	@:
