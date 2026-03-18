# Agent Failure Taxonomy


## Infrastructure Failure

- **IF-001: External API Timeout** — Agent's API call to external service exceeds timeout threshold.
- **IF-002: FileLock Contention** — Agent waits >10s for concurrent file lock, indicating resource contention.
- **IF-003: Service Unavailable** — Required service (MCP server, backend API) is unreachable.
- **IF-004: Resource Exhaustion** — System runs out of memory, disk space, or other resources.

## Planner Failure

- **PF-001: Wrong File Selected** — Agent modifies a file outside the task's declared file_scope.
- **PF-002: Dependency Violation** — Agent acts on a task before its dependencies are complete.
- **PF-003: Security Zone Misclassification** — Agent treats a critical/sensitive file as normal.
- **PF-004: Scope Creep** — Agent touches files outside the task scope.
- **PF-005: Deferred-Pod Violation** — Agent works on a deactivated/deferred feature area.

## Tool Failure

- **TF-001: Invalid Arguments** — Agent passes invalid arguments to a tool call.
- **TF-002: Parse Error** — Agent cannot parse tool response or provides malformed input.
- **TF-003: Idempotency Violation** — Agent performs a non-idempotent action that was already done.
- **TF-004: Side-Effect Error** — Tool call produces unintended side effects.

## Safety Violation

- **SV-001: Secret Exposure** — Agent reads, outputs, or transmits secrets (.env, tokens, API keys).
- **SV-002: Destructive Action** — Agent performs irreversible destructive operation.
- **SV-003: Unauthorized Zone Access** — Agent modifies 🔴-zone file without escalation.
- **SV-004: Data Integrity Violation** — Agent modifies tests to make them pass instead of fixing source code.

## Recovery Success

- **RP-001: Successful Retry** — Agent retries the same approach after a transient failure and succeeds.
- **RP-002: Alternative Approach** — Agent recognizes failure and switches to a different strategy.
- **RP-003: Graceful Degradation** — Agent produces partial result and documents what's missing.
- **RP-004: Correct Escalation** — Agent recognizes its own limitation and asks for human help.
