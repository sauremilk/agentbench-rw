"""Tests for failure taxonomy."""

from agentbench.taxonomy import TAXONOMY, get_category, get_description, taxonomy_summary
from agentbench.types import FailureCategory, FailureCode


class TestTaxonomy:
    def test_all_codes_present(self):
        for code in FailureCode:
            assert code in TAXONOMY, f"{code} missing from TAXONOMY"

    def test_get_category(self):
        assert get_category(FailureCode.IF_001) == FailureCategory.INFRASTRUCTURE

    def test_get_description_returns_string(self):
        desc = get_description(FailureCode.IF_001)
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_unknown_code_returns_fallback(self):
        # Functions use fallback values, not None
        assert get_category("NOT_A_CODE") == FailureCategory.TOOL  # type: ignore[arg-type]
        assert get_description("NOT_A_CODE") == "Unknown failure"  # type: ignore[arg-type]

    def test_taxonomy_summary_contains_all_codes(self):
        md = taxonomy_summary()
        for code in FailureCode:
            assert code.value in md

    def test_each_entry_has_required_keys(self):
        required = {"category", "name", "description", "impact", "example"}
        for code, entry in TAXONOMY.items():
            assert required.issubset(entry.keys()), f"{code} missing keys: {required - entry.keys()}"

    def test_safety_violations_correct_category(self):
        assert get_category(FailureCode.SV_001) == FailureCategory.SAFETY_VIOLATION
        assert get_category(FailureCode.SV_002) == FailureCategory.SAFETY_VIOLATION

    def test_recovery_patterns_have_category(self):
        assert get_category(FailureCode.RP_001) == FailureCategory.RECOVERY
