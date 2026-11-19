## ADDED Requirements

### Requirement: Git Ingestion and Diff Metadata Extraction (ID: FR-001)
The system SHALL ingest commits, changed file paths/diffs, and pull/merge request status metadata from configured GitHub/GitLab repositories for specified time windows.

#### Scenario: Ingest commits and file changes from a repository
- **GIVEN** a configured repository `repo-a` and a lookback window
- **WHEN** the ingestion job runs
- **THEN** the system retrieves commit metadata (SHA, author, timestamp, message), changed file lists/diffs, and associated PR/MR states

### Requirement: Noise Filtering and Pre-Scoring Before LLM (ID: FR-002)
The system SHALL deterministically filter out noise commits without LLM calls and assign a pre-score based on touched artifact paths and optional text markers.

#### Scenario: Drop non-contract noise commits before LLM validation
- **GIVEN** commits classified as merge commits, `chore`/`docs`/`lint`/`typo`-only changes, or edits outside tracked public/shared artifacts
- **WHEN** the pre-filter evaluates the commits
- **THEN** the system excludes them from LLM validation and records them in filtering metrics

### Requirement: Cross-Repository Artifact Graph Construction (ID: FR-003)
The system SHALL build and query a cross-repository artifact dependency graph linking contracts, packages, and schemas to dependent repositories and owning teams.

#### Scenario: Link consumer repository to source contract artifact
- **GIVEN** repository `repo-a` defines contract artifact `billing-api.yaml` owned by `team-billing` and repository `repo-b` (`team-mobile`) declares a dependency on it
- **WHEN** the artifact graph is constructed or updated
- **THEN** a directed dependency edge is recorded from `repo-b` (`team-mobile`) to `billing-api.yaml` in `repo-a` (`team-billing`)

### Requirement: Implicit Blocker Detection via Silence Window (ID: FR-004)
The system SHALL identify candidate cross-team blockers when an artifact in repository A changes, dependent repository B has a recorded dependency on it, and no corresponding adaptation commit/PR/issue activity occurs in B within a configurable window of `N` days.

#### Scenario: Flag candidate blocker when dependent repo shows no reaction within N days
- **GIVEN** a contract artifact in `repo-a` changes at timestamp `T0` and `repo-b` depends on it with silence window `N` days
- **WHEN** the evaluator checks `repo-b` at `T0 + N days` and finds no matching follow-up commit, PR, or issue activity
- **THEN** the pair `(repo-a change, repo-b dependency)` is emitted as a blocker candidate

### Requirement: Cost-Aware LLM Risk Validation and Dependency Map (ID: FR-005)
The system SHALL validate blocker candidates using an LLM only after deterministic pre-filtering and graph candidate pairing, producing a risk score and structured `DEPENDENCY_MAP` output.

#### Scenario: Score candidate compatibility risk and generate dependency map
- **GIVEN** a candidate pair `(repo-a change, repo-b dependency)`
- **WHEN** the LLM validation step evaluates the contract change against consumer context
- **THEN** the system assigns a risk score, incompatibility assessment, and evidence references in the resulting `DEPENDENCY_MAP`

### Requirement: MCP Tools Interface for Dependency and Risk Queries (ID: FR-006)
The system SHALL expose MCP tools allowing agents and operators to query cross-team dependencies, candidate implicit blockers, and risk scores.

#### Scenario: Query active implicit blockers via MCP tool
- **GIVEN** an evaluated dependency graph and risk assessment dataset
- **WHEN** a client invokes the MCP blocker query tool with optional team or repository filters
- **THEN** the system returns matching blocker candidates, risk scores, and `trace_id` correlation metadata

### Requirement: Non-Functional Performance and Reliability (ID: NFR-001)
The system SHALL serve MCP/query requests with latency `p95 <= 2000ms`, maintain availability `>= 99.5%`, and keep error rate `<= 1%` across runtime operations.

#### Scenario: Meet p95 latency and error rate under expected load
- **GIVEN** runtime requests executed against the service within target concurrency
- **WHEN** telemetry is aggregated over the evaluation window
- **THEN** request duration `p95` is `<= 2000ms`, error rate is `<= 1%`, and availability is `>= 99.5%`

### Requirement: Non-Functional Security for Tokens and Repository Metadata (ID: NFR-SEC-001)
The system SHALL prevent exposure of Git/LLM credentials and untrusted repository text injection into privileged agent tool execution.

#### Scenario: Redact secrets and isolate untrusted commit/PR text
- **GIVEN** ingested commit messages, diffs, or PR descriptions containing untrusted text or sensitive tokens
- **WHEN** data is processed, logged, or passed to LLM/MCP layers
- **THEN** credentials are redacted/masked and untrusted repository strings are treated as untrusted data rather than instructions

### Requirement: Non-Functional Observability Telemetry and Correlation (ID: NFR-OBS-001)
The system SHALL emit OpenTelemetry metrics, structured logs, and distributed traces with `trace_id` correlation and PII/secret redaction across runtime operations.

#### Scenario: Correlate HTTP/MCP request trace across metrics and logs
- **GIVEN** an incoming request with optional W3C `traceparent` / `X-Request-ID` headers
- **WHEN** the request executes ingestion, filtering, graph lookup, or LLM validation
- **THEN** metrics, logs, and spans share the active `trace_id` and satisfy latency/error SLOs without leaking secrets

## Observability Contract

| Сигнал | Тип | Когда создаётся | Обязательные атрибуты | Куда экспортируется |
|--------|-----|-----------------|----------------------|---------------------|
| `dep_agent.request.duration` | metric (histogram) | каждый MCP/HTTP запрос | `operation`, `status`, `trace_id` | Prometheus |
| `dep_agent.commits.filtered_total` | metric (counter) | прохождение пре-фильтра | `repo`, `outcome` (`kept`/`dropped`), `trace_id` | Prometheus |
| `dep_agent.llm.validation.duration` | metric (histogram) | вызов LLM для пары кандидатов | `model`, `risk_level`, `trace_id` | Prometheus |
| `dep_agent.run.span` | span | выполнение анализа/запроса | `repo.source`, `repo.target`, `trace_id` | OpenTelemetry Collector / Jaeger |
| `dep_agent.blocker.detected` | log (structured) | выявлен кандидат на блокировку | `source_repo`, `target_repo`, `risk_score`, `trace_id` | Loki |
| `security.secret.redacted` | log (audit) | редактирование токена/секрета | `secret_type`, `component`, `trace_id` | Loki |

## SLO

| SLO | Целевое значение | Как измеряется |
|-----|------------------|----------------|
| Latency p95 | `<= 2000ms` | `dep_agent.request.duration` histogram `p95` |
| Availability | `>= 99.5%` | Доля успешных запросов/проверок за период |
| Error rate | `<= 1%` | Доля запросов со статусом ошибки (`error` / `5xx`) за период |