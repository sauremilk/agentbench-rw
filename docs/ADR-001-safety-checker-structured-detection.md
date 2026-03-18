# ADR-001: Safety Checker — Structured Regex Detection

**Status:** Accepted  
**Date:** 2026-06-27  
**Deciders:** Code-Review → Implementation  

## Context

The original `SafetyChecker` detected secrets and destructive operations by
converting the entire `event.data` dict to a string and checking for substrings:

```python
# BEFORE — naive string matching
data_str = str(event.data).lower()
if any(p in data_str for p in self._SECRET_PATTERNS):
    ...
```

This produced **false positives** on common English words that happened to be
pattern substrings (e.g. `"token"` flagged legitimate prose about token
counting; `"password"` flagged documentation mentioning password policies).

The review classified this as **Kritisch**: a safety instrument that cries wolf
trains users to ignore its output, defeating its purpose.

## Decision

Replace the string-coercion approach with **three compiled regex pattern sets**
that inspect values at the appropriate granularity:

| Pattern Set | Scope | Examples |
|---|---|---|
| `_SECRET_FILE_RE` | `event.file_path` only | `.env`, `id_rsa`, `*.pem`, `credentials.json` |
| `_SECRET_VALUE_RE` | Individual string values in `event.data` | `api_key=`, `sk-proj-...`, `AKIA...`, `ghp_...` |
| `_DESTRUCTIVE_RE` | Individual string values in `event.data` | `rm -rf`, `git push --force`, `DROP TABLE` |

Key design choices:

1. **Structured field inspection** — `_iter_string_values()` recursively
   extracts all string values from nested dicts/lists, then each value is
   checked individually. This avoids false matches from dict keys, class names,
   or repr artifacts.

2. **Assignment-context patterns** — Words like `password` and `token` are only
   flagged when followed by `=` or `:`, indicating they carry an actual secret
   value rather than appearing in prose.

3. **Key-format patterns** — OpenAI (`sk-`), Stripe (`pk-`), GitHub (`ghp_`),
   and AWS (`AKIA`) keys are matched by their well-known prefixes + minimum
   length, not by generic words.

4. **File-path patterns** — Checked separately against `event.file_path` (not
   serialized data), because a file named `.env` is always suspicious regardless
   of its content.

## Consequences

### Positive
- **Zero false positives** on the documented regression cases (token counting,
  password-in-prose, generic "secret" in comments).
- **Structured detection** means adding new patterns is a one-line regex
  addition — no risk of matching unrelated serialized content.
- **Testable** — 15 targeted unit tests + property-based tests via hypothesis
  verify both true-positive and true-negative invariants.

### Negative
- Regex patterns must be maintained as new key formats emerge (e.g. new cloud
  provider prefixes).
- Deep nesting in `event.data` is recursively traversed — pathological inputs
  could be slow (mitigated by real-world data being shallow).

### Neutral
- Zone-based detection logic is unchanged — this ADR only covers pattern-based
  detection.

## References
- Review finding: *"Kritisch — safety_checker.py false positives on 'token'"*
- Implementation: `agentbench/instruments/safety_checker.py`
- Tests: `tests/test_instruments.py::TestSafetyChecker`
