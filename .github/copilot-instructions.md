# GitHub Copilot — AgentBench-RW Workspace Instructions

## Projektkontext

**AgentBench-RW** ist ein Real-World Evaluation Framework für KI-Coding-Agenten.
Es misst Agenten in 7 Dimensionen: Correctness, Containment, Safety, Cost, Latency, Autonomy, Explainability.

```
agentbench/
├── types.py          ← Kern-Datenstrukturen (AgentTrace, EvalResult, ...)
├── taxonomy.py       ← Scenario- und Policy-Klassifikation
├── runner.py         ← Benchmark-Ausführung
├── scoring.py        ← Score-Berechnung (7 Dimensionen)
├── config.py         ← Konfiguration
├── cli.py            ← CLI-Interface
├── adapters/         ← Agent-Adapter (pro LLM-Provider)
├── instruments/      ← Mess-Instrumente (cost, containment, latency, ...)
├── policies/         ← Containment- und Safety-Policies
├── report/           ← Report-Generierung (HTML, JSON)
├── scenarios/        ← Benchmark-Szenarien
└── traces/           ← Trace-Parsing und -Replay
```

---

## Commit-Workflow (automatisch für alle Agenten)

Jede Änderung gehört zu einem Task. Kein Code ohne Task-Referenz.

### Ablauf (Pflicht)

```
1. Task in tasks.md lesen (ID + Acceptance Criteria)
2. Betroffene Datei + Test-Datei lesen (nie blind schreiben)
3. Implementieren (vollständig, typisiert, kein Placeholder)
4. Tests:   pytest tests/ -v --tb=short -q --timeout=60
5. Lint:    ruff check agentbench/ --fix && ruff format agentbench/
6. Committen — Format: <type>(<modul>): <beschreibung> (TASK-XXX)
```

### Commit-Format

```
<type>(<modul>): <kurze Beschreibung auf Englisch> (TASK-XXX)

- <Acceptance Criterion 1> ✅
- <Acceptance Criterion 2> ✅
```

**Types:** `feat` · `fix` · `refactor` · `perf` · `test` · `docs` · `chore` · `ci`

**Beispiele:**
```
feat(scoring): add containment F1 calculation (TASK-003)
fix(runner): handle empty trace list gracefully (TASK-007)
test(policies): add unit tests for SafetyGatePolicy (TASK-012)
```

### Verboten

- Commits ohne `(TASK-XXX)` Referenz
- Mehrere unabhängige Features in einem Commit
- Commits mit roten Tests oder Ruff-Fehlern
- `git push` ohne explizite User-Freigabe

---

## Code-Konventionen

| Regel | Detail |
|-------|--------|
| **Python** | 3.11+, Type Hints überall, Ruff (120 Zeichen) |
| **Imports** | Schwere Deps (`torch`, `transformers`) IMMER lazy (in Funktionen) |
| **Vollständigkeit** | Kein `# TODO: implement` — vollständig oder `raise NotImplementedError(...)` |
| **Tests** | Jede neue öffentliche Funktion braucht einen Test in `tests/` |
| **Secrets** | Niemals im Code — nur über Umgebungsvariablen |

---

## Qualitäts-Gates (nach jeder Änderung)

```bash
ruff check agentbench/ --fix && ruff format agentbench/
pytest tests/ -v --tb=short -q --timeout=60
```

Tests rot → **sofort fixen**, keine weiteren Änderungen.

---

## Prompt für vollständige Task-Umsetzung

`.github/prompts/task-executor.prompt.md` — führt durch alle 6 Phasen automatisch.
