# Policy Comparison — Vorher/Nachher

**Generated:** 2026-03-18 06:09 UTC
**Traces evaluated:** 4 (4 files)

---

## Vorher/Nachher-Tabelle

| Metric | v0 (Null) | v1 (Rule-Based) | v2 (Tuned) | Δ v0→v2 |
|--------|-----------|-----------------|------------|---------|
| Recall | 0.00 | 1.00 | 1.00 | — |
| Precision | 0.00 | 0.83 | 1.00 | — |
| F1 | 0.00 | 0.91 | 1.00 | — |
| FN Rate | 1.00 | 0.00 | 0.00 | **-100%** |
| Composite Score | 83.8 | 88.2 | 88.8 | **+6%** |
| Safety Pass Rate | 100% | 100% | 100% | — |

---

## Full Variant Comparison

| Variant | Confidence | Budget | Retries | F1 | Recall | Precision | Composite | Safety |
|---------|-----------|--------|---------|-----|--------|-----------|-----------|--------|
| null-v0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 83.8 | 100% |
| rule-based-v1 | 0.3 | 1.5 | 2 | 0.909 | 1.000 | 0.833 | 88.2 | 100% |
| tuned-v2 **⬅ BEST** | 0.45 | 1.2 | 2 | 1.000 | 1.000 | 1.000 | 88.8 | 100% |

---

## Key Findings

1. **Containment Recall** went from 0.00 to 1.00 (v0 = no escalation)
2. **Containment F1** improved from 0.00 to 1.00
3. **False Negative Rate** reduced from 1.00 to 0.00
4. **Composite Score** improved from 83.8 to 88.8
5. **v2 vs v1:** Precision improved 0.83 → 1.00 (fewer false positives while maintaining recall)
6. **Safety** maintained at 100% pass rate across all variants

---

## Reproduction

```bash
# Install
pip install -e ".[dev]"

# Generate baselines (3× per scenario)
python scripts/generate_baselines.py --runs 3

# Regenerate this comparison
python scripts/generate_comparison.py

# Or via CLI
agentbench optimize --traces-dir results/baseline/ --output results/optimization.md
```
