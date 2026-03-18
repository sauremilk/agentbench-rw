---
applyTo: "**/*.py"
---

# Python-Instruktionen — AgentBench-RW

## Pflichtregeln für jede Python-Datei

### Type Annotations

- Vollständige Annotations auf **allen** öffentlichen Funktionen und Methoden.
- `list[X]` statt `List[X]`, `dict[K, V]` statt `Dict[K, V]` (Python 3.11+).
- `Any` nur wenn unvermeidbar und dann mit Kommentar begründen.

### Imports

- Schwere Abhängigkeiten (`torch`, `transformers`, `onnxruntime`, `cv2`) **immer lazy** — in Funktionen, nie auf Modul-Ebene:

  ```python
  # ❌ Falsch
  import torch

  # ✅ Richtig
  def compute_embeddings(text: str) -> list[float]:
      import torch
      ...
  ```

- Absolute Imports bevorzugen: `from agentbench.types import AgentTrace`

### Vollständigkeit

- Keine `# TODO: implement`-Stubs — entweder vollständig implementieren oder:
  ```python
  raise NotImplementedError("TASK-XXX: [was fehlt]")
  ```

### Fehlerbehandlung

- Eigene Exception-Klassen von `AgentBenchError` ableiten (in `agentbench/types.py`).
- Alle Randfälle explizit behandeln: leere Listen, `None`-Werte, leere Strings.

### Tests

- Jede neue öffentliche Funktion/Klasse braucht einen Test in `tests/test_<modul>.py`.
- Kein echter Netzwerkzugriff in Unit-Tests — externe Deps mocken.

## Selbst-Review vor jedem Commit

- [ ] Type Annotations auf allen öffentlichen Funktionen?
- [ ] Keine Secrets im Code?
- [ ] Input-Validierung an Systemgrenzen?
- [ ] Lazy Imports für schwere Abhängigkeiten?
- [ ] Tests grün: `pytest tests/ -v --tb=short -q --timeout=60`?
- [ ] Ruff sauber: `ruff check agentbench/ --fix && ruff format agentbench/`?
