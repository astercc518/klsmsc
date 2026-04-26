# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

考拉出海（Kaolach）国际短信网关系统。Multi-tenant SMS gateway with a Telegram business bot, admin console, and customer portal. All UI strings are bilingual (zh-CN primary, en fallback).

## Commands

### Backend (FastAPI)

```bash
# Run API server (dev, inside container)
docker compose exec api uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Apply DB migrations (runs automatically on container start via docker-entrypoint.sh)
docker compose exec api alembic upgrade head

# Create a new migration
docker compose exec api alembic revision --autogenerate -m "describe_change"

# Restart a specific service after code change
docker compose restart api
docker compose restart worker
docker compose restart beat

# Full rebuild (when requirements.txt or Dockerfile changes)
docker compose build api && docker compose up -d api
# Worker uses the same image as API — rebuild both:
docker compose build worker && docker compose up -d worker beat
```

### Frontend (Vue 3 + Vite)

```bash
# Dev server (hot reload)
cd frontend && npm run dev

# Production build (must use docker build to catch TS errors)
docker compose build frontend && docker compose up -d frontend

# Lint
cd frontend && npm run lint
```

**Important:** `docker compose restart frontend` does NOT switch to a newly built image. Always use `docker compose up -d frontend` after a build.

### Workers

```bash
# View worker logs
docker compose logs worker -f --tail=100
docker compose logs beat -f --tail=20

# Celery queues: sms_send, sms_dlr, sms_result_queue, data_tasks, webhook_tasks, integrations, web_automation
```

## Architecture

### Services (docker-compose)

| Container | Role |
|---|---|
| `smsc-api` | FastAPI app, port 8000 |
| `smsc-worker` | Celery worker (same image as api) |
| `smsc-beat` | Celery beat scheduler |
| `smsc-frontend` | Nginx serving Vite SPA, ports 80/443 |
| `smsc-mysql` | MySQL 8 |
| `smsc-proxysql` | ProxySQL connection pool (API/worker connect here, not MySQL directly) |
| `smsc-redis` | Redis 7 — no password in this deployment |
| `smsc-rabbitmq` | RabbitMQ message broker |
| `smsc-docker-proxy` | tecnativa/docker-socket-proxy — restricted Docker API for container restart |
| `smsc-bot` | Telegram Bot process |
| `smsc-smpp-gateway` | Go SMPP gateway (connects upstream SMPP providers, publishes DLRs) |

### Backend Structure (`backend/app/`)

- **`api/v1/`** — FastAPI routers. Each file is a feature domain (`sms.py`, `admin.py`, `batches.py`, `system_config.py`, `admin_logs.py`, `security_logs.py`, etc.). Route prefixes are set in `main.py`.
- **`modules/`** — SQLAlchemy ORM models, organized by domain (`common/`, `sms/`, `data/`, `water/`).
- **`core/`** — Business logic: `auth.py` (JWT + API Key), `pricing.py`, `router.py` (channel routing), `dlr_handler.py`, `audit.py`.
- **`workers/`** — Celery tasks. `celery_app.py` defines queues and beat schedule. Worker processes use `NullPool` (not the async engine) because Celery forks.
- **`services/`** — Shared service layer: `operation_log.py` (write audit trail), `config_service.py`, `notification_service.py`.
- **`utils/`** — Stateless helpers: `cache.py` (Redis singleton), `queue.py`, `validator.py`, `sms_template.py`.
- **`config.py`** — Pydantic `Settings` class; reads from environment variables.

### Authentication

Two auth paths share `core/auth.py`:
- **Admin (JWT Bearer)**: `Authorization: Bearer <jwt>` → `Depends(get_current_admin)`. Tokens stored in `localStorage.admin_token`.
- **Customer (API Key)**: `X-API-Key: ak_xxx` or `Authorization: Bearer ak_xxx` → `Depends(get_current_account)`. The frontend interceptor in `api/index.ts` decides which header to send based on URL prefix.

Admin roles: `super_admin` > `admin` > `staff`. Role checks are inline in route handlers via `_require_admin()`.

### Database

- MySQL 8 via ProxySQL → `asyncmy` async driver → SQLAlchemy async sessions.
- **Schema changes go through Alembic only** — no `create_all` in code. The entrypoint runs `alembic upgrade head` with 40 retries before starting the app.
- Key tables: `sms_logs` (partitioned by month, ~960 bytes/row), `sms_batch`, `data_numbers`, `private_library_numbers`, `admin_operation_log`, `config_audit_log`, `system_config`.

### Celery / Task Flow

SMS send path: API enqueues `send_sms_task` → `sms_send` queue → `sms_worker.py`. Batch send: `batch_worker.py` reads CSV, splits into chunks, enqueues individual SMS tasks. DLR path: SMPP gateway or HTTP callback → `process_dlr_task` → `sms_dlr` queue → `dlr_handler.py`. Results buffer via `sms_result_queue` → `sms_worker.py:process_sms_result_task`.

**Critical constraint:** Celery workers use `NullPool` for DB connections (set in each worker file's engine creation). Never reuse the API's async engine in worker code.

### Redis Usage

- No auth (`redis-server --appendonly yes`, no `--requirepass`). Never add `REDIS_PASSWORD` env var.
- Cache keys of interest: `admin:monthly_commission:{YYYY-MM}` (30min TTL), `data:my_numbers:summary:*` / `data:my_numbers:stale:*` (Redis-only — do not use in-process cache for these).
- `get_cache_manager()` returns a wrapper with in-process L1 + Redis L2. For cross-process keys (worker ↔ API) always use `get_redis_client()` directly.

### Frontend Structure (`frontend/src/`)

- **`views/`** — Page components, mirroring the route tree. Admin pages under `views/admin/`, customer under `views/account/`, system under `views/system/`.
- **`api/`** — One file per backend domain, all using the shared `request` axios instance from `api/index.ts`.
- **`config/system_config_meta.ts`** — Single source of truth for the 33 system config items: labels, UI type, validation, restart hints. Update here when adding new config keys.
- **`stores/`** — Pinia stores: `auth.ts`, `app.ts`.
- **`router/routes/admin.ts`** — Admin route definitions. `/admin/system/config` resolves through `views/system/Index.vue` which embeds `Config.vue` as a tab.

### System Config Page

`views/system/Config.vue` is embedded in `views/system/Index.vue` (tabs: Config / Logs / Services / Security). The new design (implemented 2026-04) uses:
- Left nav with 5 groups (basic/sms/notification/telegram/security)
- `dirtyKeys` Set for batch-save tracking
- `SensitiveInput.vue` — locked by default, requires confirm to edit, re-locks after save
- `AuditLogDrawer.vue` — right-side drawer, timeline view of `config_audit_log`

### Operation Logging

All admin mutations should call `services/operation_log.py:log_operation()` with `module`, `action`, `title`, and optional `detail` dict. Modules: `system`, `account`, `channel`, `sms`, `finance`, `security`, `config`, `login`.

### Go SMPP Gateway (`go-smpp-gateway/`)

Standalone Go service. Connects to upstream SMPP providers, receives DLR reports, publishes them to RabbitMQ (`sms_dlr` queue). Exposes a probe HTTP endpoint (`SMPP_GATEWAY_PROBE_URL`). Not part of the Python build pipeline.
