"""Tests for ORCID input parsing in link_author_authorities example."""

import importlib.util
from pathlib import Path

import pytest


def _load_link_script():
    path = Path(__file__).resolve().parents[1] / "examples" / "link_author_authorities.py"
    spec = importlib.util.spec_from_file_location("link_author_authorities", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def laa():
    return _load_link_script()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0000-0002-1825-0097", "0000000218250097"),
        ("0000-0002-1825-009X", "000000021825009X"),
        ("0000-0002-1825-009x", "000000021825009X"),
        ("https://orcid.org/0000-0002-1825-0097", "0000000218250097"),
        ("https://www.orcid.org/0000-0002-1825-009X", "000000021825009X"),
        ("http://ORCID.org/0000-0001-2345-6789", "0000000123456789"),
        ("orcid.org/0000-0001-2345-6789", "0000000123456789"),
        ("www.orcid.org/0000-0001-2345-6789", "0000000123456789"),
        ("https://orcid.org/0000-0001-2345-6789?lang=en", "0000000123456789"),
        ("0000000123456789", "0000000123456789"),
        ("See https://www.orcid.org/0000-0001-2345-6789 for profile", "0000000123456789"),
    ],
)
def test_normalize_orcid_success(laa, raw, expected):
    assert laa.normalize_orcid_identifier(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not-an-orcid",
        "0000-0001-2345",  # too short
        "0000-0001-2345-678",  # too short
    ],
)
def test_normalize_orcid_rejects_invalid(laa, raw):
    assert laa.normalize_orcid_identifier(raw) is None


def test_normalize_rejects_bad_checksum_position(laa):
    assert laa.normalize_orcid_identifier("0000-0002-1825-X097") is None


def test_orcid_hyphenated_from_compact(laa):
    assert laa.orcid_hyphenated_from_compact("0000000168849316") == "0000-0001-6884-9316"
    assert laa.orcid_hyphenated_from_compact("000000021825009X") == "0000-0002-1825-009X"
    assert laa.orcid_hyphenated_from_compact("bad") is None


def test_extract_orcid_person_identifier(laa):
    entry = {
        "metadata": {
            "person.identifier.orcid": [{"value": "0000-0001-6884-9316"}],
        }
    }
    url = laa.extract_orcid_from_entry(entry, None)
    assert laa.normalize_orcid_identifier(url or "") == "0000000168849316"


def test_extract_orcid_person_identifier_compact_plain(laa):
    entry = {"metadata": {"person.identifier.orcid": [{"value": "0000000168849316"}]}}
    url = laa.extract_orcid_from_entry(entry, None)
    assert laa.normalize_orcid_identifier(url or "") == "0000000168849316"


def test_extract_orcid_dc_identifier_uri(laa):
    entry = {
        "metadata": {
            "dc.identifier.uri": [
                {"value": "https://orcid.org/0000-0001-6884-9316"},
            ],
        }
    }
    url = laa.extract_orcid_from_entry(entry, None)
    assert laa.normalize_orcid_identifier(url or "") == "0000000168849316"


def test_extract_orcid_detail_other_information_person(laa):
    entry: dict = {"metadata": {}}
    detail = {
        "otherInformation": {
            "person.identifier.orcid": "0000-0001-6884-9316",
        }
    }
    url = laa.extract_orcid_from_entry(entry, detail)
    assert laa.normalize_orcid_identifier(url or "") == "0000000168849316"


@pytest.mark.parametrize(
    "item_author,authority_name,expected",
    [
        # Item metadata "Given, Family" vs vocabulary "Family, Given"
        ("Bert, Bogaerts", "Bogaerts, Bert", True),
        # Symmetric when both use same order
        ("Bogaerts, Bert", "Bogaerts, Bert", True),
        ("Bert, Bogaerts", "Bert, Bogaerts", True),
        # Regression: initials and exact first name (authority = Family, First)
        ("Smith, J.", "Smith, John", True),
        ("Smith, John", "Smith, John", True),
        ("Doe, J. M.", "Doe, Jane Marie", True),
        # Different people
        ("Smith, John", "Doe, Jane", False),
        ("Bert, Bogaerts", "Other, Person", False),
        # Deduped identical comma parts (single variant)
        ("Smith, Smith", "Smith, Smith", True),
    ],
)
def test_fuzzy_match_author_name_order_and_regression(laa, item_author, authority_name, expected):
    assert laa.fuzzy_match_author(item_author, authority_name) is expected
