# Cross-Team Implicit Dependency Risk Agent

[![CI](https://github.com/realrvs/ai-crossteam-risk-agent/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/realrvs/ai-crossteam-risk-agent/actions/workflows/ci-cd.yml)
[![codecov](https://codecov.io/gh/realrvs/ai-crossteam-risk-agent/branch/main/graph/badge.svg)](https://codecov.io/gh/realrvs/ai-crossteam-risk-agent)

Агент выявления неявных межкомандных блокировок по изменениям контрактов/артефактов в Git и окну тишины в зависимых репозиториях с MCP-интерфейсом, риск-скорингом и наблюдаемостью по принципу Observability by Design.

## Зачем это нужно

Анализ строится как cost-aware воронка:
1. Ingestion — сбор метаданных коммитов, диффов/файлов и статусов PR/MR/issue из GitHub/GitLab API (FR-001).
2. Pre-filter (без LLM) — отсев шума (merge, chore, docs, lint, typo, неконтрактные пути) и пре-скоринг (FR-002).
3. Artifact Graph & Silence Window (N дней) — граф зависимостей с привязкой к командам и поиск пар изменение в A <-> зависимость в B без реакции в B за окно N дней (FR-003, FR-004).
4. LLM Risk Validator — оценка совместимости и риска на отобранных кандидатах с изоляцией недоверенных данных и формированием DEPENDENCY_MAP (FR-005).
5. MCP & Query Interface — выдача зависимостей, блокировок и риск-скоров с пробросом trace_id (FR-006).

## Безопасность и наблюдаемость

- Угрозы: OWASP Top 10 for LLM + STRIDE (TM-01..TM-04, NFR-SEC-001..NFR-SEC-004) — изоляция untrusted-текстов репозиториев, SecretRedactor и аудит security.secret.redacted, read-only доступ к Git API, лимит кандидатов на LLM.
- Наблюдаемость: otel, prometheus, grafana, loki; SLO: latency p95 <= 2000ms, availability >= 99.5%, error rate <= 1%; корреляция через W3C traceparent и X-Request-ID.

## Статус

Спецификация и дизайн готовы в каталоге openspec/ (proposal, specs, design, threat-model, adr, api-contract, test-specs, tasks, apply, context, traceability-matrix).
