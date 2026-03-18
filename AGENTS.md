# AGENTS.md — AI Agent Instructions for AgentBench-RW

Dieses Dokument gibt KI-Assistenten (GitHub Copilot, Claude, GPT-4) klare Anweisungen für die Arbeit an AgentBench-RW.

---

## Verhaltensprinzipien

1. **Lies zuerst, schreib dann.** Betroffene Datei UND zugehörige Test-Datei lesen, bevor Änderungen gemacht werden.
2. **Kein Overengineering.** Nur genau das implementieren was angefordert wird. Keine zusätzlichen Features, Abstraktionen oder "Future-Proofing".
3. **Vollständigkeit.** Keine `# TODO: implement`-Platzhalter — Methoden sind vollständig oder explizit `raise NotImplementedError("...")`.
4. **Lazy Imports.** Schwere Abhängigkeiten (`torch`, `transformers`, etc.) IMMER innerhalb von Funktionen importieren, nie auf Modul-Ebene.
5. **Type Annotations überall.** Alle öffentlichen Funktionen und Klassen vollständig annotiert (PEP 484/526).

---

## Commit-Workflow (PFLICHT für Agenten)

Agenten arbeiten Task-basiert — ein Task = ein atomarer Commit. Kein Code landet ohne zugehörigen Task.

### Schritt-für-Schritt

```
1. Task in tasks.md lesen (Acceptance Criteria verstehen)
2. Kontext laden (betroffene Dateien + Tests lesen)
3. Implementieren (vollständig, typisiert, kein Placeholder)
4. Qualitätsprüfung (Type Annotations, keine Secrets, Input-Validierung)
5. Tests ausführen:  pytest tests/ -v --tb=short -q --timeout=60
6. Lint:             ruff check agentbench/ --fix && ruff format agentbench/
7. Committen (siehe Format unten)
```

### Commit-Format

```
<type>(<modul>): <kurze Beschreibung auf Englisch> (TASK-XXX)

- <Acceptance Criterion 1> ✅
- <Acceptance Criterion 2> ✅
```

**Erlaubte Types:**

| Type | Wann |
|------|------|
| `feat` | Neue Funktionalität |
| `fix` | Bugfix |
| `refactor` | Code-Umstrukturierung ohne Verhaltensänderung |
| `perf` | Performance-Verbesserung |
| `test` | Tests hinzufügen oder korrigieren |
| `docs` | Dokumentation |
| `chore` | Build, Dependencies, Config |
| `ci` | CI/CD-Konfiguration |

**Beispiele:**

```
feat(scoring): add containment F1 calculation (TASK-003)

- ContainmentInstrument returns precision, recall, F1 ✅
- Unit tests cover true/false positive cases ✅
```

```
fix(runner): handle empty trace list gracefully (TASK-007)

- Runner returns empty EvalResult instead of raising KeyError ✅
- Regression test added ✅
```

### Verboten

- Commits ohne Task-Referenz
- Mehrere unabhängige Features in einem Commit
- Commits mit roten Tests
- Commits mit Ruff-Fehlern

---

## Prompt-Workflow

Für vollständige Task-Umsetzung: `.github/prompts/task-executor.prompt.md`

Der Prompt führt durch alle 6 Phasen (Lesen → Kontext → Implementieren → QC → Tests → Commit) und erzwingt das korrekte Commit-Format.

---

## Modul-Struktur

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

## Backlog

Tasks sind in `tasks.md` definiert. Vor jeder Implementierung dort nachschauen.

**Neuen Task hinzufügen:**

```markdown
#### TASK-XXX
**Status:** `open`
**Modul:** `agentbench/<modul>/`
**Beschreibung:** ...
**Acceptance Criteria:**
- [ ] ...
```

---

## Qualitäts-Gates

Nach jeder Änderung:

```bash
ruff check agentbench/ --fix && ruff format agentbench/
pytest tests/ -v --tb=short -q --timeout=60
```

Tests rot nach Code-Änderung → **sofort fixen**, nichts anderes tun.
