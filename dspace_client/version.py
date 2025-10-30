"""Version compatibility system for DSpace client."""

from dataclasses import dataclass
from typing import List, Dict, Optional, Union
from .exceptions import VersionIncompatibilityError


@dataclass
class DSpaceVersion:
    """Represents a DSpace version."""
    major: int
    minor: int
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"
    
    @classmethod
    def from_string(cls, version_str: str) -> "DSpaceVersion":
        """Create DSpaceVersion from string like '7.6' or '8.0'."""
        try:
            major, minor = version_str.split('.')
            return cls(int(major), int(minor))
        except ValueError:
            raise ValueError(f"Invalid version string: {version_str}")
    
    @property
    def version_string(self) -> str:
        """Get version as string."""
        return str(self)


class VersionCompatibility:
    """
    Validates API operations against target DSpace version(s).
    
    CRITICAL: Every API call is validated before execution.
    """
    
    # Supported DSpace versions
    SUPPORTED_VERSIONS = {
        "bleeding-edge": ["bleeding-edge"],  # Latest development
        "7.0": ["7.0", "7.1", "7.2", "7.3", "7.4", "7.5", "7.6"],
        "8.0": ["8.0"],
        "9.0": ["9.0"],
    }
    
    # Method compatibility matrix
    # Each method lists the minimum version that supports it
    COMPATIBILITY = {
        # Core CRUD operations (available in all versions)
        "create_community": ["7.0+"],
        "delete_community": ["7.0+"],
        "create_collection": ["7.0+"],
        "delete_collection": ["7.0+"],
        "create_item": ["7.0+"],
        "delete_item": ["7.0+"],
        "create_bundle": ["7.0+"],
        "upload_bitstream": ["7.0+"],
        "delete_bitstream": ["7.0+"],
        
        # EPerson operations
        "create_eperson": ["7.0+"],
        "delete_eperson": ["7.0+"],
        "add_eperson_to_group": ["7.0+"],
        
        # Group operations
        "create_group": ["7.0+"],
        "delete_group": ["7.0+"],
        "search_group_by_name": ["7.0+"],
        "find_or_create_group": ["7.0+"],
        "add_subgroup_to_group": ["7.0+"],
        
        # Collection default groups
        "create_collection_item_read_group": ["7.0+"],
        "create_collection_bitstream_read_group": ["7.0+"],
        
        # Statistics
        "create_item_view": ["7.0+"],
        
        # Future methods might be version-specific
        # "create_workflow_item": ["8.0+"],  # Example of version-specific method
    }
    
    def __init__(self, target_versions: Union[str, List[str]], docs_fetcher=None):
        """
        Initialize validator with target versions.
        
        Args:
            target_versions: Single version string or list of versions to validate against
            docs_fetcher: Optional fetcher with loaded REST contract docs
        """
        if isinstance(target_versions, str):
            self.target_versions = [target_versions]
        else:
            self.target_versions = target_versions
        
        self.docs_fetcher = docs_fetcher
        
        # Validate that all target versions are supported
        for version in self.target_versions:
            if version not in self.SUPPORTED_VERSIONS:
                raise ValueError(f"Unsupported DSpace version: {version}")
    
    def validate_before_call(self, method_name: str, endpoint: str, operation: str) -> None:
        """
        Validate operation is compatible with ALL target versions.
        
        Called automatically before every API call.
        
        Args:
            method_name: Name of the method being called
            endpoint: API endpoint path
            operation: HTTP operation (GET, POST, PUT, DELETE)
        
        Raises:
            VersionIncompatibilityError: If operation not supported in any target version
        """
        # Check if method is in compatibility matrix
        if method_name not in self.COMPATIBILITY:
            # If not in matrix, assume it's supported in all versions
            return
        
        required_versions = self.COMPATIBILITY[method_name]
        
        # Check if any target version is incompatible
        incompatible_versions = []
        for target_version in self.target_versions:
            if not self._is_version_compatible(target_version, required_versions):
                incompatible_versions.append(target_version)
        
        if incompatible_versions:
            # Find which versions DO support this operation
            supported_versions = []
            for version in self.target_versions:
                if self._is_version_compatible(version, required_versions):
                    supported_versions.append(version)
            
            raise VersionIncompatibilityError(
                operation=method_name,
                target_versions=self.target_versions,
                supported_versions=supported_versions,
                message=(
                    f"Operation '{method_name}' not supported in DSpace version(s): {', '.join(incompatible_versions)}. "
                    f"Supported in: {', '.join(supported_versions) if supported_versions else 'none'}. "
                    f"Consider using target_versions={supported_versions} or implement workaround."
                )
            )
    
    def _is_version_compatible(self, version: str, required_versions: List[str]) -> bool:
        """Check if a version is compatible with required versions."""
        if version == "bleeding-edge":
            # Bleeding edge supports everything
            return True
        
        # Check if version matches any requirement
        for required in required_versions:
            if required.endswith("+"):
                # Version range like "7.0+" means 7.0 and above
                min_version = required[:-1]
                if self._version_compare(version, min_version) >= 0:
                    return True
            elif version == required:
                # Exact version match
                return True
        
        return False
    
    def _version_compare(self, version1: str, version2: str) -> int:
        """Compare two version strings. Returns -1, 0, or 1."""
        try:
            v1 = DSpaceVersion.from_string(version1)
            v2 = DSpaceVersion.from_string(version2)
            
            if v1.major != v2.major:
                return -1 if v1.major < v2.major else 1
            if v1.minor != v2.minor:
                return -1 if v1.minor < v2.minor else 1
            return 0
        except ValueError:
            # If version parsing fails, assume incompatible
            return -1
    
    def get_compatibility_report(self) -> Dict[str, List[str]]:
        """Generate report of which operations work with which versions."""
        report = {}
        
        for method_name, required_versions in self.COMPATIBILITY.items():
            compatible_versions = []
            for target_version in self.target_versions:
                if self._is_version_compatible(target_version, required_versions):
                    compatible_versions.append(target_version)
            
            report[method_name] = compatible_versions
        
        return report
    
    def get_incompatible_operations(self) -> Dict[str, List[str]]:
        """Get operations that are incompatible with current target versions."""
        incompatible = {}
        
        for method_name, required_versions in self.COMPATIBILITY.items():
            incompatible_versions = []
            for target_version in self.target_versions:
                if not self._is_version_compatible(target_version, required_versions):
                    incompatible_versions.append(target_version)
            
            if incompatible_versions:
                incompatible[method_name] = incompatible_versions
        
        return incompatible
