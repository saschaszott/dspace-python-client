"""Centralized exceptions for DSpace client."""

from typing import List, Optional


class DSpaceClientError(Exception):
    """Base exception for all DSpace client errors."""
    pass


class AuthenticationError(DSpaceClientError):
    """Raised when authentication fails."""
    pass


class DSpaceAPIError(DSpaceClientError):
    """Raised when DSpace API returns an error."""
    pass


class VersionIncompatibilityError(DSpaceClientError):
    """Raised when an operation is not compatible with target DSpace version(s)."""
    
    def __init__(
        self, 
        operation: str, 
        target_versions: List[str], 
        supported_versions: List[str],
        message: Optional[str] = None
    ):
        self.operation = operation
        self.target_versions = target_versions
        self.supported_versions = supported_versions
        
        if message is None:
            missing_versions = set(target_versions) - set(supported_versions)
            message = (
                f"Operation '{operation}' not supported in DSpace version(s): {', '.join(missing_versions)}. "
                f"Supported versions: {', '.join(supported_versions)}. "
                f"Consider using target_versions={supported_versions} or implement workaround."
            )
        
        super().__init__(message)


class DocumentationError(DSpaceClientError):
    """Raised when documentation fetching or validation fails."""
    pass


class NetworkError(DSpaceClientError):
    """Raised when network operations fail."""
    pass
