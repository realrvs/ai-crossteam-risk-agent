# Cross-Team Implicit Dependency Risk Agent

[![CI](https://github.com/realrvs/ai-crossteam-risk-agent/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/realrvs/ai-crossteam-risk-agent/actions/workflows/ci-cd.yml)
[![codecov](https://codecov.io/gh/realrvs/ai-crossteam-risk-agent/branch/main/graph/badge.svg)](https://codecov.io/gh/realrvs/ai-crossteam-risk-agent)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenSpec](https://img.shields.io/badge/spec-OpenSpec-violet.svg)](openspec/)

Агент выявления неявных межкомандных блокировок по изменениям контрактов/артефактов в Git и окну тишины в зависимых репозиториях. Использует cost-aware воронку с детерминированным пре-фильтром, графом зависимостей и LLM-валидацией (YandexGPT).

## Оглавление

- [О проекте](#о-проекте)
- [Архитектура](#архитектура)
- [Функциональные требования](#функциональные-требования)
- [Безопасность](#безопасность)
- [Наблюдаемость (Observability)](#наблюдаемость-observability)
- [Структура проекта](#структура-проекта)
- [Установка и запуск](#установка-и-запуск)
- [API](#api)
- [Тесты](#тесты)
- [Спецификация](#спецификация)
- [Roadmap](#roadmap)

## О проекте

При разработке в крупных организациях команды меняют API-контракты, protobuf-схемы и зависимости пакетов, не всегда уведомляя зависимые репозитории. Это приводит к **неявным блокировкам** — когда одна команда ломает контракт, а другая об этом узнаёт только при падении сборки.

**Dep Agent** решает эту проблему, автоматически:
1. Сканируя изменения контрактов во всех репозиториях
2. Строя граф зависимостей между командами
3. Выявляя "окна тишины" — когда зависимый репозиторий не отреагировал на изменение
4. Оценивая риск через LLM и формируя структурированный DEPENDENCY_MAP

**Ключевые решения:**
- DEC-001: Окно тишины — API=7д, манифесты=3д
- DEC-002: Маппинг команд — CODEOWNERS + YAML fallback
- DEC-003: Артефакты v1 — OpenAPI, Protobuf, package manifests
- DEC-004: Хранилище — SQLite (MVP) → PostgreSQL
- DEC-005: LLM-провайдер — YandexGPT

## Архитектура

```
┌──────────────────────────────────────────────────────────────────┐
│                        dep_agent (Python 3.12)                   │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│ Ingestion│ Filtering│  Graph   │ Detector │  LLM     │   API    │
│          │          │          │          │ Validator│          │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┤
│                   Security & Observability Layer                │
│  SecretRedactor │ OTel SDK │ Prometheus │ Loki │ Grafana        │
└──────────────────────────────────────────────────────────────────┘
```

**Cost-aware воронка:**
1. **Ingestion** — сбор метаданных из GitHub/GitLab API
2. **Pre-filter** — отсев merge/chore/docs/lint/typo (без LLM)
3. **Artifact Graph** — граф зависимостей + silence window detector
4. **LLM Validator** — оценка риска только для отобранных кандидатов (max 20)
5. **API** — выдача результатов через REST + MCP

## Функциональные требования

| ID | Описание | Источник |
|----|----------|----------|
| **FR-001** | Ingestion коммитов, диффов, PR/MR статусов | `ingestion/service.py` |
| **FR-002** | Детерминированный pre-filter шума | `filtering/pre_filter.py` |
| **FR-003** | Граф зависимостей + маппинг на команды | `graph/artifact_graph.py` |
| **FR-004** | Детектор окна тишины N дней | `detector/silence_detector.py` |
| **FR-005** | LLM Risk Validator (YandexGPT) | `validator/llm_validator.py` |
| **FR-006** | Query API + MCP handlers | `api/handlers.py` |

## Безопасность

| Угроза | Митигация | Файл |
|--------|-----------|------|
| **TM-01** — Untrusted data | Изоляция system/user промптов, ADR-001 | `validator/llm_validator.py` |
| **TM-02** — Information Disclosure | SecretRedactor (GitHub/GitLab/Yandex/AWS tokens) | `security/redactor.py` |
| **TM-03** — Excessive access | Read-only Git API, MCP validation | `ingestion/git_client.py` |
| **TM-04** — Resource exhaustion | Candidate cap (20), rate-limit backoff | `validator/llm_validator.py` |

## Наблюдаемость (Observability)

| Компонент | Метрики / Логи | SLO |
|-----------|----------------|-----|
| **OpenTelemetry** | `dep_agent.run.span`, W3C traceparent | p95 ≤ 2000ms |
| **Prometheus** | `request.duration`, `commits.filtered_total`, `llm.validation.duration` | avail ≥ 99.5% |
| **Loki** | `dep_agent.blocker.detected`, `security.secret.redacted` | error ≤ 1% |
| **Grafana** | 8-panel dashboard (RED metrics, funnel, blockers) | — |

## Структура проекта

```
src/dep_agent/
├── config.py                    # YAML config loader + env overrides
├── graph/
│   ├── models.py                # SQLAlchemy 2.0 (artifact_nodes, edges, silence_candidates, dependency_map)
│   └── artifact_graph.py        # Dependency graph + TeamMapper (CODEOWNERS/YAML)
├── ingestion/
│   ├── git_client.py            # Read-only GitHub/GitLab API client
│   └── service.py               # Ingestion orchestration
├── filtering/
│   └── pre_filter.py            # Noise filter (merge/chore/docs/lint/typo)
├── detector/
│   └── silence_detector.py      # N-day silence window blocker detector
├── security/
│   └── redactor.py              # Secret redactor (GitHub/GitLab/Yandex/AWS tokens)
├── validator/
│   └── llm_validator.py         # YandexGPT risk validator + DEPENDENCY_MAP
├── api/
│   └── handlers.py              # WSGI API (3 endpoints + trace_id middleware)
├── telemetry/
│   └── otel_setup.py            # OTel SDK + Prometheus metrics
└── observability/
    ├── grafana_dashboard.py     # 8-panel Grafana dashboard
    ├── alert_rules.py           # 6 Prometheus alert rules
    └── loki_queries.py          # 6 Loki log query templates
```

## Установка и запуск

```bash
# Установка зависимостей
pip install -e ".[dev]"

# Запуск тестов
pytest tests/ -v

# Запуск с OTel console exporter
export OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
python -c "from dep_agent.telemetry.otel_setup import setup_otel; setup_otel('otlp-grpc')"
```

## API

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `GET` | `/v1/dependencies` | Список зависимостей (params: `team`, `repo`) |
| `GET` | `/v1/blockers` | Список блокировок (params: `team`, `min_risk_score`) |
| `POST` | `/v1/analysis/runs` | Запуск анализа (body: `repositories`, `lookback_days`) |
| `GET` | `/health` | Health check |

**Response headers:** `X-Trace-Id`, `X-Request-ID` (W3C traceparent correlation)

## Тесты

```bash
# Все тесты (112 passed)
pytest tests/ -v

# По категориям
pytest tests/test_artifact_graph.py -v    # Graph + TeamMapper
pytest tests/test_pre_filter.py -v        # Noise filter
pytest tests/test_silence_detector.py -v  # Silence window
pytest tests/test_llm_validator.py -v     # LLM validation
pytest tests/test_api_handlers.py -v      # API endpoints
pytest tests/test_synthetic_pipeline.py -v # End-to-end synthetic test
pytest tests/test_observability.py -v     # Dashboard + alerts + Loki
```

## Спецификация

Полная спецификация проекта в каталоге `openspec/`:

| Файл | Описание |
|------|----------|
| `proposal.md` | Зачем и что строим |
| `context.md` | Контекст, threat model, решения DEC-001..DEC-005 |
| `design.md` | Архитектура, компоненты, Mermaid-диаграммы |
| `spec.md` | 6 FR + 3 NFR с BDD-сценариями |
| `threat-model.md` | OWASP Top 10 for LLM + STRIDE, 4 угрозы |
| `api-contract.yaml` | OpenAPI 3.1, 3 endpoint'а |
| `tasks.md` | 10 задач в 3 фазах |
| `apply.md` | Миграции, feature flags, canary deployment |
| `traceability-matrix.md` | Прослеживаемость FR→TM→ADR→Tasks→Tests |
| `test-specs/workflow/tests.md` | 11 тест-кейсов |
| `adr/ADR-001` | Cost-Aware Funnel and Untrusted-Data Isolation |
| `adr/ADR-002` | Secret Redaction Gate and Correlation Propagation |

## Roadmap

| Версия | Статус | Содержание |
|--------|--------|------------|
| **v0.1** | ✅ Реализовано | Skeleton, config, graph, ingestion, pre-filter, silence detector, LLM validator, API, observability |
| **v0.2** | 🔄 В работе | CI/CD (GitHub Actions), Docker + docker-compose, MCP Server |
| **v0.3** | 📋 Планируется | PostgreSQL миграция, DB migrations, multi-instance deployment |
| **v1.0** | 📋 Планируется | Production readiness, CODEOWNERS parser, external team registry |
