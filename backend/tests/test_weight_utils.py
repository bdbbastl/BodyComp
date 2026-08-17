import pytest

from app.utils.weight import parse_weight_kg


def test_parses_float_directly():
    assert parse_weight_kg(76.05) == 76.05


def test_parses_comma_string():
    assert parse_weight_kg("76,05") == 76.05


def test_parses_dot_string():
    assert parse_weight_kg("76.05") == 76.05


def test_rounds_to_nearest_0_05():
    assert parse_weight_kg("76.03") == 76.05
    assert parse_weight_kg("76.01") == 76.0


def test_none_and_empty_string_return_none():
    assert parse_weight_kg(None) is None
    assert parse_weight_kg("") is None
    assert parse_weight_kg("   ") is None


def test_invalid_string_raises_value_error():
    with pytest.raises(ValueError):
        parse_weight_kg("not a number")
