import pytest

from dspace_client.exceptions import VersionIncompatibilityError
from dspace_client.version import VersionCompatibility


def test_check_server_version_compatibility_accepts_prefixed_version():
    """
    Server version strings like 'DSpace 7.6' should be normalized to '7.6'
    and treated as an exact match when target_versions includes '7.6'.
    """
    is_compatible, warning = VersionCompatibility.check_server_version_compatibility(
        "DSpace 7.6", ["7.6", "8.0"]
    )
    assert is_compatible is True
    assert warning is None


@pytest.mark.parametrize(
    ("target_version", "required", "expected"),
    [
        ("7.6", ["7.0+"], True),
        ("6.6", ["7.0+"], False),
        ("8.0", ["8.0"], True),
        ("bleeding-edge", ["7.0+"], True),
    ],
)
def test_is_version_compatible(target_version, required, expected):
    validator = VersionCompatibility("7.6")
    assert validator._is_version_compatible(target_version, required) is expected


def test_validate_before_call_raises_for_incompatible_operation():
    validator = VersionCompatibility(["7.0"])
    validator.COMPATIBILITY["create_item"] = ["8.0+"]

    with pytest.raises(VersionIncompatibilityError, match="create_item"):
        validator.validate_before_call(
            method_name="create_item",
            endpoint="core/items",
            operation="POST",
        )


def test_validate_before_call_allows_unlisted_methods():
    validator = VersionCompatibility(["7.0"])
    validator.validate_before_call(
        method_name="unknown_future_method",
        endpoint="core/items",
        operation="GET",
    )
