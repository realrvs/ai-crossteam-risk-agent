## Миграции
- [ ] `001_init_artifact_graph`: Создание таблиц артефактов, связей зависимостей между репозиториями/командами, окон тишины `N` и записей `DEPENDENCY_MAP` (`migrations/001_init_artifact_graph.sql`)
- [ ] Rollback: Откат миграции `001_init_artifact_graph` через удаление таблиц `dependency_map`, `silence_candidates`, `artifact_edges`, `artifact_nodes` (`migrations/001_init_artifact_graph.down.sql`)

## Feature Flags
| Flag | Default | TTL | Связанный FR | Связанный TM |
|---|---|---|---|---|
| `dep_agent.llm_validation.enabled` | `true` | 30d | FR-005 | TM-01, TM-04 |
| `dep_agent.secret_redaction.strict` | `true` | 30d | FR-002, NFR-SEC-002 | TM-02 |
| `dep_agent.mcp_server.enabled` | `true` | 30d | FR-006 | TM-03 |

## Canary Deployment
1. Deploy canary 5% трафика (или на пилотный набор репозиториев) с включённой телеметрией и `SecretRedactor`.
2. Monitor SLO canary vs baseline:
   - p95 latency ≤ `2000ms`
   - error rate ≤ `1%`
   - availability ≥ `99.5%`
3. **Auto-rollback при degradation > 10% по любому SLO**
   - Trigger: Prometheus alert `SloDegradation` fires
   - Action: отключение соответствующего feature flag (`dep_agent.llm_validation.enabled` / `dep_agent.mcp_server.enabled`) → ротация pods → rollback deployment
4. Если canary stable 24h → 50% → 100%.
5. Зафиксировать конфигурацию прогона и очистить временные флаги после стабилизации.

## **Observability Verification**
> Проверка, что сигналы из Observability Contract реально видны в бэкендах.
- [ ] В Grafana виден дашборд с RED-метриками и метриками фильтрации/LLM (`dep_agent.request.duration`, `dep_agent.commits.filtered_total`, `dep_agent.llm.validation.duration`)
- [ ] В Loki есть логи с `trace_id` для тестового запроса, включая `dep_agent.blocker.detected`
- [ ] В OTel Collector / Jaeger виден трейс `dep_agent.run.span`, связанный с входящим `traceparent` / `trace_id`
- [ ] Prometheus: алерты на деградацию SLO (`p95 > 2000ms`, `error rate > 1%`) и rate-limit срабатывают на тестовом сценарии
- [ ] `security.secret.redacted` audit-лог фиксируется при маскировании тестового токена и не содержит сырых секретов
- [ ] Retention policy для логов/метрик/трейсов настроена и не хранит сырые токены или несанитизированные диффы

## Rollback Plan
1. Перевести feature flag `dep_agent.llm_validation.enabled` и `dep_agent.mcp_server.enabled` в безопасное/выключенное состояние при необходимости.
2. Откатить релиз сервиса на предыдущую стабильную версию контейнера.
3. При необходимости выполнить откат миграции БД (`001_init_artifact_graph.down.sql`).
4. Проверить восстановление метрик (`dep_agent.request.duration`, error rate ≤ `1%`, availability ≥ `99.5%`) и логов в Loki/Prometheus/Grafana.