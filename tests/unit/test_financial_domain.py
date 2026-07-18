"""
Unit tests for financial_domain.

Tests cover:
- normalize_partner: known raw name → canonical group
- normalize_partner: unknown name → lowercased passthrough
- normalize_partner: case-insensitive input
- normalize_partner: non-string input returned as-is
- normalize_partner: all variants of multi-variant groups resolve correctly
- get_partner_sql_variants: known group → full variant list
- get_partner_sql_variants: unknown group → [group_name] fallback
- get_partner_sql_variants: case-insensitive group lookup
- partner_in_clause: generates correct SQL IN fragment
- partner_in_clause: custom column name used
- partner_in_clause: unknown group → single-variant IN clause
- partner_in_clause: multi-variant group → all variants quoted
"""

import pytest

from src.utils.financial_domain import (
    PARTNER_GROUPS,
    get_partner_sql_variants,
    normalize_partner,
    partner_in_clause,
)

# ── normalize_partner ──────────────────────────────────────────────────────────

class TestNormalizePartner:

    def test_exact_canonical_name(self):
        assert normalize_partner("gopay") == "gopay"

    def test_raw_variant_resolves_to_group(self):
        assert normalize_partner("gopay_wec") == "gopay"
        assert normalize_partner("gopay_basic") == "gopay"

    def test_linkaja_all_variants(self):
        for raw in PARTNER_GROUPS["linkaja"]:
            assert normalize_partner(raw) == "linkaja", f"Failed for raw: {raw}"

    def test_case_insensitive(self):
        assert normalize_partner("GoPay") == "gopay"
        assert normalize_partner("DANA_WEC") == "dana"
        assert normalize_partner("LinkAja") == "linkaja"

    def test_unknown_name_lowercased_passthrough(self):
        assert normalize_partner("UnknownPartner") == "unknownpartner"

    def test_non_string_returned_as_is(self):
        assert normalize_partner(None) is None
        assert normalize_partner(123) == 123

    def test_telkomsel_wallet_variants(self):
        assert normalize_partner("telkomsel_wallet") == "telkomsel_wallet"
        assert normalize_partner("tsel_wallet") == "telkomsel_wallet"

    def test_shopeepay_variants(self):
        assert normalize_partner("shopeepay_basic") == "shopeepay"
        assert normalize_partner("shopeepay_wec") == "shopeepay"


# ── get_partner_sql_variants ───────────────────────────────────────────────────

class TestGetPartnerSqlVariants:

    def test_known_group_returns_all_variants(self):
        variants = get_partner_sql_variants("linkaja")
        assert "linkaja" in variants
        assert "linkaja_app" in variants
        assert "linkajawco" in variants

    def test_unknown_group_returns_single_fallback(self):
        variants = get_partner_sql_variants("mysterious_bank")
        assert variants == ["mysterious_bank"]

    def test_case_insensitive_lookup(self):
        variants_lower = get_partner_sql_variants("gopay")
        variants_upper = get_partner_sql_variants("GoPay")
        assert variants_lower == variants_upper

    def test_all_groups_return_non_empty_list(self):
        for group in PARTNER_GROUPS:
            variants = get_partner_sql_variants(group)
            assert isinstance(variants, list)
            assert len(variants) > 0

    def test_single_variant_group(self):
        assert get_partner_sql_variants("qris") == ["qris"]
        assert get_partner_sql_variants("indomaret") == ["indomaret"]


# ── partner_in_clause ──────────────────────────────────────────────────────────

class TestPartnerInClause:

    def test_default_column_name(self):
        result = partner_in_clause("gopay")
        assert result.startswith("partner IN (")

    def test_custom_column_name(self):
        result = partner_in_clause("gopay", column="payment_provider")
        assert result.startswith("payment_provider IN (")

    def test_all_variants_quoted(self):
        result = partner_in_clause("linkaja")
        for variant in PARTNER_GROUPS["linkaja"]:
            assert f"'{variant}'" in result

    def test_unknown_group_single_variant_clause(self):
        result = partner_in_clause("new_partner")
        assert result == "partner IN ('new_partner')"

    def test_sql_fragment_valid_format(self):
        """Result must follow: column IN ('v1', 'v2', ...)"""
        result = partner_in_clause("dana")
        assert "IN (" in result
        assert result.endswith(")")
        assert "'" in result

    def test_multi_variant_group_no_duplicates(self):
        result = partner_in_clause("ovo")
        # Count occurrences of 'ovo' in the IN list
        variants = get_partner_sql_variants("ovo")
        for v in variants:
            assert result.count(f"'{v}'") == 1
