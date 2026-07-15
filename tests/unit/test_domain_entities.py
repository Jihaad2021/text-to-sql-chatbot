"""
Unit tests — domain_entities helpers (src/utils/domain_entities.py).

Covers:
  1. Partner helpers: canonical list, display list, variants, keywords, render blocks.
  2. Channel helpers: codes, keywords, render blocks, rewrite rules.
  3. Cache-clear portability: adding a partner to YAML propagates to all helpers.
"""

from pathlib import Path

import pytest
import yaml

from src.utils.domain_entities import (
    _load,
    get_channel_codes,
    get_channel_keywords,
    get_partner_canonical_list,
    get_partner_display_list,
    get_partner_keywords,
    get_partner_variants,
    render_channel_codes_flat,
    render_channel_group_labels_block,
    render_channel_groups_block,
    render_channel_list_block,
    render_channel_rewrite_rules,
    render_partner_display_block,
    render_partner_list_block,
)

_YAML_PATH = Path(__file__).parent.parent.parent / "config" / "domain_entities.yaml"


# ── Partner helpers ───────────────────────────────────────────────────────────

class TestPartnerList:
    def test_canonical_list_has_9_partners(self):
        assert len(get_partner_canonical_list()) == 9

    def test_canonical_list_contains_all_expected(self):
        lst = get_partner_canonical_list()
        for name in ("dana", "finnet", "gopay", "indomaret", "linkaja",
                     "ovo", "qris", "shopeepay", "telkomsel_wallet"):
            assert name in lst, f"{name!r} missing from canonical list"

    def test_display_list_has_9_partners(self):
        assert len(get_partner_display_list()) == 9

    def test_display_list_contains_gopay(self):
        assert "GoPay" in get_partner_display_list()

    def test_display_list_contains_telkomsel_wallet(self):
        assert "Telkomsel Wallet" in get_partner_display_list()

    def test_render_partner_list_block_contains_all_canonicals(self):
        block = render_partner_list_block()
        for name in ("dana", "finnet", "gopay", "indomaret", "linkaja",
                     "ovo", "qris", "shopeepay", "telkomsel_wallet"):
            assert name in block

    def test_render_partner_display_block_contains_display_names(self):
        block = render_partner_display_block()
        for name in ("Dana", "GoPay", "LinkAja", "QRIS", "Telkomsel Wallet"):
            assert name in block


class TestPartnerVariants:
    def test_linkaja_has_6_variants(self):
        variants = get_partner_variants("linkaja")
        assert len(variants) == 6

    def test_linkaja_variants_contain_all_known(self):
        variants = get_partner_variants("linkaja")
        for v in ("linkaja", "linkaja_app", "linkaja_basic", "linkaja_wec",
                  "linkajawco", "linkaja_wco"):
            assert v in variants, f"Variant {v!r} missing"

    def test_qris_has_single_variant(self):
        assert get_partner_variants("qris") == ["qris"]

    def test_unknown_canonical_returns_name_itself(self):
        assert get_partner_variants("newpay") == ["newpay"]

    def test_telkomsel_wallet_variants(self):
        variants = get_partner_variants("telkomsel_wallet")
        assert "telkomsel_wallet" in variants
        assert "tsel_wallet" in variants


class TestPartnerKeywords:
    def test_keywords_is_frozenset(self):
        assert isinstance(get_partner_keywords(), frozenset)

    def test_keywords_contains_canonical_names(self):
        kws = get_partner_keywords()
        for name in ("dana", "gopay", "ovo", "qris", "shopeepay"):
            assert name in kws

    def test_keywords_are_lowercase(self):
        kws = get_partner_keywords()
        for kw in kws:
            assert kw == kw.lower(), f"Keyword {kw!r} is not lowercase"


# ── Channel helpers ───────────────────────────────────────────────────────────

class TestChannelCodes:
    def test_all_codes_present(self):
        codes = get_channel_codes()
        for code in ("i1", "f0", "f4", "f5", "b0", "b3", "a0", "ig"):
            assert code in codes, f"Code {code!r} missing"

    def test_channel_codes_flat_contains_all(self):
        flat = render_channel_codes_flat()
        for code in ("i1", "f0", "f4", "f5", "b0", "b3", "a0", "ig"):
            assert code in flat

    def test_8_codes_total(self):
        assert len(get_channel_codes()) == 8


class TestChannelKeywords:
    def test_keywords_is_frozenset(self):
        assert isinstance(get_channel_keywords(), frozenset)

    def test_keywords_are_lowercase(self):
        kws = get_channel_keywords()
        for kw in kws:
            assert kw == kw.lower()

    def test_umb_in_keywords(self):
        assert "umb" in get_channel_keywords()

    def test_wec_in_keywords(self):
        assert "wec" in get_channel_keywords()

    def test_mytelkomsel_app_in_keywords(self):
        assert "mytelkomsel app" in get_channel_keywords()


class TestChannelRenderBlocks:
    def test_channel_list_block_format(self):
        block = render_channel_list_block()
        # Should have code=label format for each group
        assert "i1=MyTelkomsel App" in block
        assert "f0/f4/f5=UMB" in block
        assert "b0/b3/a0=WEC" in block
        assert "ig=MyTelkomsel Basic" in block

    def test_channel_group_labels_block(self):
        block = render_channel_group_labels_block()
        assert "MyTelkomsel App" in block
        assert "UMB" in block
        assert "WEC" in block
        assert "MyTelkomsel Basic" in block

    def test_channel_groups_block_format(self):
        block = render_channel_groups_block()
        # Should have label (codes) format
        assert "MyTelkomsel App (i1)" in block
        assert "UMB (f0/f4/f5)" in block
        assert "WEC (b0/b3/a0)" in block
        assert "MyTelkomsel Basic (ig)" in block

    def test_channel_rewrite_rules_includes_all_groups(self):
        rules = render_channel_rewrite_rules()
        assert "channel = 'i1'" in rules
        assert "channel IN (f0" in rules or "channel IN ('f0'" in rules
        assert "channel IN (b0" in rules or "channel IN ('b0'" in rules
        assert "channel = 'ig'" in rules

    def test_channel_rewrite_rules_has_multiple_keywords_for_app(self):
        rules = render_channel_rewrite_rules()
        assert "MyTelkomsel App" in rules
        assert "aplikasi mytelkomsel" in rules

    def test_channel_rewrite_rules_has_multiple_keywords_for_basic(self):
        rules = render_channel_rewrite_rules()
        assert "MyTelkomsel Basic" in rules
        assert "basic" in rules


# ── Portability: adding a partner propagates to all helpers ──────────────────

class TestPortabilityNewPay:
    """
    Simulates adding a new partner "newpay" to domain_entities.yaml.
    Verifies all render functions return the new partner WITHOUT code changes.
    The _load() cache is cleared before/after to simulate a restart.
    """

    def _add_newpay(self) -> None:
        data = yaml.safe_load(_YAML_PATH.read_text())
        data["partners"].append({
            "canonical": "newpay",
            "display":   "NewPay",
            "variants":  ["newpay"],
            "keywords":  ["newpay"],
        })
        _YAML_PATH.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
        _load.cache_clear()

    def _remove_newpay(self) -> None:
        data = yaml.safe_load(_YAML_PATH.read_text())
        data["partners"] = [p for p in data["partners"] if p["canonical"] != "newpay"]
        _YAML_PATH.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
        _load.cache_clear()

    def setup_method(self):
        self._add_newpay()

    def teardown_method(self):
        self._remove_newpay()

    def test_canonical_list_has_10_partners(self):
        assert len(get_partner_canonical_list()) == 10
        assert "newpay" in get_partner_canonical_list()

    def test_render_partner_list_block_contains_newpay(self):
        assert "newpay" in render_partner_list_block()

    def test_render_partner_display_block_contains_newpay(self):
        assert "NewPay" in render_partner_display_block()

    def test_partner_keywords_contains_newpay(self):
        assert "newpay" in get_partner_keywords()

    def test_partner_count_reflects_new_partner(self):
        assert len(get_partner_canonical_list()) == 10
