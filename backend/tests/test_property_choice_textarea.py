"""
===============================================================================
BLOCK COMMENT: CHOICE / TEXTAREA PROPERTY NORMALIZATION TESTS
Reference: EPIC-NODE-PROPS-UI-001 / STORY-CHOICE-TEXTAREA-VALUES-001
Description:
    DB-free unit tests for app.nodes.properties helpers:
      1. Empty `value` falls back to `default`.
      2. Legacy comma-separated choice options in `value` lift into `options`.
      3. Single-select choice with no value/default resolves to first option.
      4. Multi-select choice keeps list values and is not split into options.
===============================================================================
"""

from app.nodes.properties import (
    normalize_choice_entry,
    property_entries_to_dict,
    resolve_entry_value,
)


def test_empty_value_falls_back_to_default():
    entries = [{"key": "action", "type": "choice", "value": "", "default": "highlight",
                "options": ["highlight", "redact"]}]
    assert property_entries_to_dict(entries) == {"action": "highlight"}


def test_textarea_default_used_when_value_missing():
    entries = [{"key": "strong_words", "type": "textarea", "default": "a, b, c"}]
    assert property_entries_to_dict(entries) == {"strong_words": "a, b, c"}


def test_legacy_comma_options_lifted_from_value():
    entry = {"key": "query_type", "type": "choice", "value": "insert,update,delete,select", "default": ""}
    norm = normalize_choice_entry(entry)
    assert norm["options"] == ["insert", "update", "delete", "select"]
    assert norm["value"] == ""
    assert resolve_entry_value(entry) == "insert"
    # original entry not mutated
    assert entry["value"] == "insert,update,delete,select"


def test_multi_select_keeps_list_value():
    entry = {"key": "langs", "type": "choice", "multiple": True,
             "options": ["en", "fr", "de"], "value": ["en", "de"]}
    assert resolve_entry_value(entry) == ["en", "de"]
    assert normalize_choice_entry(entry)["options"] == ["en", "fr", "de"]


def test_explicit_value_wins_over_default():
    entries = [{"key": "action", "type": "choice", "value": "redact", "default": "highlight",
                "options": ["highlight", "redact"]}]
    assert property_entries_to_dict(entries) == {"action": "redact"}


def test_dict_input_passthrough():
    assert property_entries_to_dict({"a": 1}) == {"a": 1}

