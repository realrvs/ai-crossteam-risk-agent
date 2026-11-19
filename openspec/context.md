# Context
## Threat Model
- **Методология:** OWASP Top 10 for LLM + STRIDE (комбинированно)
- **Обоснование:** Наличие `ai: ["agent"]` и активов `repo-metadata`, `tokens`, `internal-schemas` в `security_context` требует анализа агентных рисков и классических угроз безопасности API/токенов/данных
- **Ключевые угрозы:** TM-01 (Risk 16, High/Critical), TM-02 (Risk 15, High/Critical), TM-03 (Risk 12, Medium/High), TM-04 (Risk 9, Medium)
## Принятые ADR
- ADR-001: Cost-Aware Funnel and Untrusted-Data Isolation in LLM Risk Validator (Accepted) — связан с TM-01, TM-04, NFR-SEC-001, NFR-OBS-001
- ADR-002: Secret Redaction Gate and Correlation Propagation Across Telemetry (Accepted) — связан с TM-02, NFR-SEC-002, NFR-OBS-001
## Согласованные endpoints
- `GET /v1/dependencies` — список кросс-репозиторных зависимостей по артефактам и командам
- `GET /v1/blockers` — запрос кандидатов на неявные блокировки и риск-скоров
- `POST /v1/analysis/runs` — запуск пайплайна ingestion, пре-фильтрации, оценки окна тишины и LLM-валидации
## **Observability**
- **Стек:** otel, prometheus, grafana, loki
- **SLO:** latency p95 <= 2000ms, availability >= 99.5%, error rate <= 1%
- **Ключевые сигналы:** `dep_agent.request.duration`, `dep_agent.commits.filtered_total`, `dep_agent.llm.validation.duration`, `dep_agent.run.span`, `dep_agent.blocker.detected`, `security.secret.redacted`
- **Redaction policy:** маскирование токенов/секретов в логах, диффах и промптах перед отправкой в LLM/Loki с записью `security.secret.redacted` и изоляцией untrusted-текстов репозиториев
- **Корреляция:** W3C `traceparent` и `X-Request-ID` с пробросом `trace_id` в спаны, метрики и логи
## Открытые вопросы
- [ ] Уточнить целевой размер окна тишины N (в днях) и правила маппинга репозиториев/файлов на команды (`CODEOWNERS` vs внешний реестр)
- [ ] Подтвердить список поддерживаемых типов артефактов для первого релиза (OpenAPI/Protobuf, манифесты пакетов, миграции БД)
- [ ] Определить целевое хранилище графа и состояния (`SQLite`/`PostgreSQL`) для детектора окна тишины `N`
## Пропущенные артефакты
- <нет>
## **Traceability Matrix (INCREMENTAL)**
| ID | Тип | Spec § | TM § | ADR | API | Task IDs | Test IDs | Verify |
|----|-----|--------|------|-----|-----|----------|----------|--------|
| FR-001 | FR | spec.md#fr-001 | — | — | `POST /v1/analysis/runs` | T-001, T-004 | TC-001 | Integration test |
| FR-002 | FR | spec.md#fr-002 | — | ADR-001 | `POST /v1/analysis/runs` | T-005 | TC-002 | Functional test |
| FR-003 | FR | spec.md#fr-003 | — | — | `GET /v1/dependencies` | T-006 | TC-003 | Integration test |
| FR-004 | FR | spec.md#fr-004 | — | — | `GET /v1/blockers`, `POST /v1/analysis/runs` | T-007 | TC-004 | Functional test |
| FR-005 | FR | spec.md#fr-005 | — | ADR-001 | `POST /v1/analysis/runs` | T-008 | TC-005 | Integration test |
| FR-006 | FR | spec.md#fr-006 | — | — | `GET /v1/dependencies`, `GET /v1/blockers` | T-009 | TC-006 | E2E test |
| NFR-001 | NFR | spec.md#nfr-001 | — | ADR-001, ADR-002 | `GET /v1/dependencies`, `GET /v1/blockers`, `POST /v1/analysis/runs` | T-003, T-004, T-009, T-010 | TC-007 | Performance + SLO metrics (`p95 <= 2000ms`, `avail >= 99.5%`, `err <= 1%`) |
| NFR-SEC-001 | NFR-SEC | spec.md#nfr-sec-001 | threat-model.md#5 (TM-01) | ADR-001 | `POST /v1/analysis/runs` | T-008 | TC-SEC-001 | Security test (untrusted isolation + schema check) |
| NFR-SEC-002 | NFR-SEC | spec.md#nfr-sec-001 | threat-model.md#5 (TM-02) | ADR-002 | `POST /v1/analysis/runs`, `GET /v1/blockers` | T-002 | TC-SEC-002 | Security test (redaction + `security.secret.redacted`) |
| NFR-SEC-003 | NFR-SEC | spec.md#nfr-sec-001 | threat-model.md#5 (TM-03) | — | `GET /v1/dependencies`, `GET /v1/blockers`, `POST /v1/analysis/runs` | T-001, T-009 | TC-SEC-003 | Security test (read-only scope + MCP validation) |
| NFR-SEC-004 | NFR-SEC | spec.md#nfr-sec-001 | threat-model.md#5 (TM-04) | ADR-001 | `POST /v1/analysis/runs` | T-005, T-008 | TC-SEC-004 | Security test (candidate cap + rate-limit handling) |
| NFR-OBS-001 | NFR-OBS | spec.md#nfr-obs-001 | threat-model.md#5 (TM-02) | ADR-001, ADR-002 | `GET /v1/dependencies`, `GET /v1/blockers`, `POST /v1/analysis/runs` | T-002, T-003, T-005, T-007, T-008, T-009, T-010 | TC-OBS-001 | Observability test + OTel signals + `trace_id` + `apply.md` verification |