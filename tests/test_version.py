import pytest

from dspace_client.exceptions import VersionIncompatibilityError
from dspace_client.version import VersionCompatibility
from dspace_client.versions import REST_CONTRACT_BRANCHES, SUPPORTED_VERSIONS


def test_dspace_10_is_supported_and_mapped():
    """DSpace 10 must be a declarable target with a RestContract branch."""
    assert "10.0" in SUPPORTED_VERSIONS
    assert REST_CONTRACT_BRANCHES.get("10.0") == "dspace-10_x"


def test_dspace_10_server_gating():
    """A DSpace 10.x server is accepted for ['10.0'] but rejected for ['9.0']."""
    ok_10, _ = VersionCompatibility.check_server_version_compatibility("10.1", ["10.0"])
    assert ok_10 is True

    ok_9, _ = VersionCompatibility.check_server_version_compatibility("10.1", ["9.0"])
    assert ok_9 is False


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
