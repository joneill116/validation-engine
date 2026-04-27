"""Tests for the path utilities."""
from __future__ import annotations

import pytest

from validation_engine.core.paths import get_path, normalize_path, path_exists


class TestNormalizePath:
    def test_strips_whitespace(self):
        assert normalize_path("  foo.bar  ") == "foo.bar"

    def test_strips_dollar_prefix(self):
        assert normalize_path("$.foo.bar") == "foo.bar"

    def test_lone_dollar_normalizes_to_empty(self):
        assert normalize_path("$") == ""

    def test_empty_passes_through(self):
        assert normalize_path("") == ""

    def test_non_string_rejected(self):
        with pytest.raises(TypeError):
            normalize_path(123)  # type: ignore[arg-type]


class TestGetPath:
    def test_top_level_field(self):
        assert get_path({"a": 1}, "a") == 1

    def test_nested_field(self):
        assert get_path({"a": {"b": {"c": 7}}}, "a.b.c") == 7

    def test_missing_returns_default(self):
        assert get_path({"a": 1}, "b", default="d") == "d"

    def test_missing_intermediate_returns_default(self):
        assert get_path({"a": {}}, "a.b.c", default=None) is None

    def test_explicit_none_value_returned(self):
        # Explicit ``None`` is a real value — get_path returns it as-is.
        assert get_path({"a": None}, "a", default="d") is None

    def test_indexing_into_list(self):
        assert get_path({"items": [{"v": 1}, {"v": 2}]}, "items.1.v") == 2

    def test_negative_index_into_list(self):
        assert get_path({"items": [10, 20, 30]}, "items.-1") == 30

    def test_index_out_of_range_default(self):
        assert get_path({"items": [1, 2]}, "items.99", default="d") == "d"

    def test_dollar_prefix_supported(self):
        assert get_path({"a": 1}, "$.a") == 1

    def test_descent_through_string_aborts(self):
        # Descending through a primitive returns default rather than blowing up.
        assert get_path({"a": "hello"}, "a.b", default=None) is None


class TestPathExists:
    def test_existing_path(self):
        assert path_exists({"a": {"b": 1}}, "a.b") is True

    def test_explicit_none_still_exists(self):
        assert path_exists({"a": None}, "a") is True

    def test_missing_path(self):
        assert path_exists({"a": {"b": 1}}, "a.c") is False
