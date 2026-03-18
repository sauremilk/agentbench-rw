---
description: "Führt einen einzelnen AgentBench-RW Task vollständig durch: Definition lesen, implementieren, testen, committen."
agent: agent
tools: ["codebase", "editFiles", "runCommands", "problems"]
---

# AgentBench-RW Task Executor

Du implementierst **genau einen Task** aus `tasks.md` vollständig — von der Definition bis zum Commit.

> **Robustheitsregeln (vor jeder Aktion anwenden):**
>
> 1. **Existenzprüfung:** Prüfe vor jedem Dateizugriff ob Datei/Verzeichnis existiert.
> 2. **OS-Erkennung:** Plattformgerechte Shell-Befehle (PowerShell auf Windows, Bash auf Linux/macOS).
> 3. **Idempotenz:** Jeder Schritt muss bei Wiederholung dasselbe Ergebnis liefern.

---

## Input

**Task-ID:** ${input:task_id:Task-ID, z.B. TASK-001}

---

## Ausführungs-Protokoll

### Phase 1 – Task-Definition lesen

1. Öffne `tasks.md` und suche nach `#### ${input:task_id}`.
2. Lies vollständig:
   - **Beschreibung** — was genau zu implementieren ist
   - **Acceptance Criteria** — deine Definition of Done
   - **Modul** — welche Dateien in `agentbench/` betroffen sind
   - **Abhängigkeiten** — prüfe ob diese auf `done` stehen
3. Falls der Task nicht gefunden wird: Abbruch mit klarer Fehlermeldung.

### Phase 2 – Kontext laden

Lese ergänzend (nur relevante Abschnitte):

- `README.md` (Architekturüberblick, 7 Dimensionen)
- `agentbench/types.py` (Kern-Typen und Datenstrukturen)
- `agentbench/taxonomy.py` (Scenario-/Policy-Klassifikation)
- Existierende Dateien im Zielmodul (lese immer vor dem Schreiben)
- `tests/` (relevante existierende Tests als Referenz)

### Phase 3 – Implementieren

**Pflichtregeln:**

- Vollständige Type Annotations (PEP 484/526), keine impliziten `Any`
- Keine `# TODO: implement` Platzhalter — vollständig oder explizit `raise NotImplementedError("${input:task_id}: ...")`
- Heavy Imports (`torch`, `transformers`, etc.) lazy importieren (in Funktionen, nicht auf Modul-Ebene)
- Neue öffentliche Funktionen/Klassen brauchen einen Test in `tests/`
- Ruff-konform (120 Zeichen, `select = ["E", "F", "I", "W", "UP", "B", "SIM", "TCH"]`)

**Modul-Struktur:**

```
agentbench/
├── types.py          ← Kern-Datenstrukturen (AgentTrace, EvalResult, ...)
├── taxonomy.py       ← Scenario- und Policy-Klassifikation
├── runner.py         ← Benchmark-Ausführung
├── scoring.py        ← Score-Berechnung (7 Dimensionen)
├── config.py         ← Konfiguration
├── cli.py            ← CLI-Interface
├── adapters/         ← Agent-Adapter (pro LLM-Provider)
├── instruments/      ← Mess-Instrumente (cost, containment, ...)
├── policies/         ← Containment- und Safety-Policies
├── report/           ← Report-Generierung
├── scenarios/        ← Benchmark-Szenarien
└── traces/           ← Trace-Parsing und -Replay
```

### Phase 4 – Qualitätsprüfung

Vor dem Commit intern prüfen:

- [ ] Type Annotations vollständig?
- [ ] Keine Secrets im Code?
- [ ] Input-Validierung an Systemgrenzen vorhanden?
- [ ] Lazy Imports für schwere Abhängigkeiten?
- [ ] Acceptance Criteria vollständig erfüllt?
- [ ] Keine ungenutzten Imports (ruff wird das flaggen)?

### Phase 5 – Tests ausführen

```bash
# Nur betroffene Tests (bevorzugen)
pytest tests/test_<modul>.py -v --tb=short -x --timeout=60

# Falls kein spezifischer Test: alle Unit-Tests
pytest tests/ -v --tb=short -q --timeout=60
```

Bei Fehlern: analysieren, beheben, wiederholen. Erst nach grünen Tests committen.

### Phase 6 – Committen

1. **Lint + Format:**
   ```bash
   ruff check agentbench/ --fix
   ruff format agentbench/
   ```

2. **Commit** mit Conventional Commits + Task-Referenz:

   ```
   <type>(<modul>): <kurze Beschreibung> (${input:task_id})

   - <Acceptance Criterion 1> ✅
   - <Acceptance Criterion 2> ✅
   ```

   Erlaubte Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `ci`, `build`

   Beispiele:
   ```
   feat(scoring): add containment F1 calculation (TASK-003)
   fix(runner): handle empty trace list gracefully (TASK-007)
   test(policies): add unit tests for SafetyGatePolicy (TASK-012)
   ```

3. **Push** (nur wenn explizit durch den Nutzer freigegeben):
   ```bash
   git push
   ```

---

## Sonderfälle

### Task unvollständig implementierbar (fehlende Dependency)

Hinterlasse einen Kommentar: `# ${input:task_id}: blocked by TASK-XXX — [Warum]`
Trage in `tasks.md` den Task als `blocked` ein und wähle den nächsten verfügbaren Task.

### Scope Creep erkannt

Wenn während der Implementierung weitere Sub-Tasks notwendig werden:
- Diese **nicht** sofort implementieren
- Kommentar `# TASK-NEW: [Beschreibung ausstehend]` hinterlassen
- Neuen Task am Ende von `tasks.md` eintragen
