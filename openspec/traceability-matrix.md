## Traceability Matrix (Final)

| ID | Тип | Spec § | TM § | ADR | API Endpoint | Task IDs | Test IDs | Verify Method |
|----|-----|--------|------|-----|-------------|----------|----------|---------------|
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

## Decision Traceability

| ID | Решение | Spec § | Task Refs | Status |
|----|---------|--------|-----------|--------|
| DEC-001 | Per-type silence windows: API=7d, packages=3d | design.md#детерминированные-правила-v1 | T-007 | Closed |
| DEC-002 | Team mapping: CODEOWNERS + YAML fallback | design.md#детерминированные-правила-v1 | T-006 | Closed |
| DEC-003 | Artifact types v1: OpenAPI, Protobuf, package manifests | design.md#детерминированные-правила-v1 | T-005 | Closed |
| DEC-004 | Graph store: SQLite MVP → PostgreSQL migration | design.md#технологический-стек | T-001, T-006 | Closed |
| DEC-005 | LLM provider: YandexGPT (YandexAI/YandexCloud) | design.md#технологический-стек | T-008 | Closed |