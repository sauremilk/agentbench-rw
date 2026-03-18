# tasks.md — AgentBench-RW Backlog

> **Schema:** Jeder Task hat eine eindeutige ID, einen Status und klare Acceptance Criteria.
> **Workflow:** Agents nutzen `.github/prompts/task-executor.prompt.md` um Tasks atomar abzuarbeiten.
> **Commit-Format:** `<type>(<modul>): <beschreibung> (TASK-XXX)`

---

## Status-Legende

| Status | Bedeutung |
|--------|-----------|
| `open` | Noch nicht begonnen |
| `in-progress` | Wird gerade bearbeitet |
| `done` | Vollständig implementiert + getestet |
| `blocked` | Wartet auf andere Task |

---

## Offene Tasks

#### TASK-001
**Status:** `open`
**Modul:** `agentbench/adapters/`
**Beschreibung:** OpenAI-Adapter implementieren — nimmt eine `AgentTrace` und normalisiert OpenAI API-Responses in das interne Format.
**Acceptance Criteria:**
- [ ] `OpenAIAdapter` Klasse mit `parse_trace(raw: dict) -> AgentTrace`
- [ ] Unterstützt GPT-4o und GPT-4-turbo Response-Formate
- [ ] Unit-Tests in `tests/test_adapter_openai.py`

#### TASK-002
**Status:** `open`
**Modul:** `agentbench/adapters/`
**Beschreibung:** Anthropic/Claude-Adapter implementieren — normalisiert Claude API-Responses in das interne `AgentTrace`-Format.
**Acceptance Criteria:**
- [ ] `AnthropicAdapter` Klasse mit `parse_trace(raw: dict) -> AgentTrace`
- [ ] Unterstützt Claude 3 Opus/Sonnet/Haiku Response-Formate
- [ ] Unit-Tests in `tests/test_adapter_anthropic.py`

#### TASK-003
**Status:** `open`
**Modul:** `agentbench/report/`
**Beschreibung:** HTML-Report-Generator erweitern — Radar-Chart der 7 Dimensionen als SVG inline einbetten.
**Acceptance Criteria:**
- [ ] `generate_radar_chart(result: EvalResult) -> str` gibt valides SVG zurück
- [ ] Chart enthält alle 7 Dimensionen mit korrekten Score-Werten
- [ ] Report-Template nutzt den neuen Chart
- [ ] Unit-Test validiert SVG-Struktur

#### TASK-004
**Status:** `open`
**Modul:** `agentbench/instruments/`
**Beschreibung:** Token-Cost-Instrument — berechnet API-Kosten pro Trace basierend auf Token-Count und Preismodell.
**Acceptance Criteria:**
- [ ] `CostInstrument` mit `measure(trace: AgentTrace) -> CostMetric`
- [ ] Preismodelle für OpenAI (GPT-4o, GPT-4-turbo) und Anthropic (Claude-3)
- [ ] Gibt `usd_cost: float` und `token_breakdown: dict` zurück
- [ ] Unit-Tests in `tests/test_instrument_cost.py`

#### TASK-005
**Status:** `open`
**Modul:** `agentbench/cli.py`
**Beschreibung:** `compare` CLI-Subcommand — vergleicht zwei Baseline-JSONL-Dateien und gibt Delta-Tabelle aus.
**Acceptance Criteria:**
- [ ] `agentbench compare <baseline_a> <baseline_b>` funktioniert
- [ ] Ausgabe zeigt Δ pro Dimension und Composite-Score
- [ ] Farbige Hervorhebung: grün = Verbesserung, rot = Regression
- [ ] Test in `tests/test_cli.py`

---

## Abgeschlossene Tasks

*(noch keine)*
