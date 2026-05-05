# ================================================================
# InfraGenie — Makefile
# Convenience targets for local development with Docker Compose.
# Usage: make <target>
# ================================================================

COMPOSE      = docker-compose
BACKEND_SVC  = backend
FRONTEND_SVC = frontend

.PHONY: help setup build up down restart logs \
        shell-backend shell-frontend \
        test lint format \
        clean prune

# ── Default target ─────────────────────────────────────────────
help:
	@echo ""
	@echo "  InfraGenie — Available make targets"
	@echo "  ────────────────────────────────────────────────────"
	@echo "  setup           Copy .env.example → .env (first-time setup)"
	@echo "  build           Build all Docker images"
	@echo "  up              Start all services in the background"
	@echo "  down            Stop and remove containers"
	@echo "  restart         Restart all services"
	@echo "  logs            Stream logs from all services"
	@echo "  shell-backend   Open bash shell in the backend container"
	@echo "  shell-frontend  Open sh shell in the frontend container"
	@echo "  test            Run pytest inside the backend container"
	@echo "  lint            Run ruff linter on backend source"
	@echo "  format          Run black formatter on backend source"
	@echo "  clean           Remove stopped containers and dangling images"
	@echo "  prune           Full Docker system prune (removes volumes!)"
	@echo ""

# ── First-time setup ───────────────────────────────────────────
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅  .env created from .env.example — fill in your secrets before running 'make up'."; \
	else \
		echo "ℹ️   .env already exists. Delete it and re-run to reset."; \
	fi

# ── Docker Compose lifecycle ───────────────────────────────────
build:
	$(COMPOSE) build --parallel

up:
	$(COMPOSE) up -d
	@echo "✅  InfraGenie is running."
	@echo "    Backend  → http://localhost:8000"
	@echo "    Frontend → http://localhost:3000"
	@echo "    API docs → http://localhost:8000/docs"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

# ── Container shells ───────────────────────────────────────────
shell-backend:
	$(COMPOSE) exec $(BACKEND_SVC) bash

shell-frontend:
	$(COMPOSE) exec $(FRONTEND_SVC) sh

# ── Testing & code quality ─────────────────────────────────────
test:
	$(COMPOSE) exec $(BACKEND_SVC) pytest tests/ -v --tb=short

lint:
	$(COMPOSE) exec $(BACKEND_SVC) bash -c "pip install -q ruff && ruff check ."

format:
	$(COMPOSE) exec $(BACKEND_SVC) bash -c "pip install -q black && black ."

# ── Cleanup ────────────────────────────────────────────────────
clean:
	$(COMPOSE) down --remove-orphans
	docker image prune -f

prune:
	@echo "⚠️  This will remove ALL unused Docker data including volumes."
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker system prune -af --volumes
