"""DSpace REST API client for Python.

A comprehensive Python client for the DSpace REST API with version-aware
compatibility checking and automatic documentation management.

Key Features:
- Version-first initialization with automatic documentation fetching
- Pre-execution validation for all API operations
- Multi-version compatibility support
- Git-based documentation management with auto-updates
- Rich console output for beautiful user experience
- Batch operations with adaptive concurrency control

Example:
    from dspace_client import DSpaceAuthClient, DSpaceClient
    
    # Authenticate
    auth = DSpaceAuthClient("https://demo.dspace.org")
    jwt, status = await auth.authenticate("user", "pass")
    
    # Create client with version specification
    client = DSpaceClient(
        base_url="https://demo.dspace.org",
        jwt_token=jwt,
        csrf_token=auth.csrf_token,
        http_client=auth.client,
        target_versions="bleeding-edge",  # or ["7.6", "8.0", "9.0"]
    )
    
    # Create a community (validated against target versions)
    community = await client.create_community("My Community")
"""

from .auth import DSpaceAuthClient
from .core import DSpaceClient
from .batch import BatchItemCreator
from .concurrency import ConcurrencyController, ConcurrencyConfig
from .exceptions import (
    DSpaceClientError,
    AuthenticationError,
    DSpaceAPIError,
    VersionIncompatibilityError,
)

__version__ = "0.1.0"
__author__ = "Bram Luyten"
__email__ = "bram@atmire.com"

__all__ = [
    # Main client classes
    "DSpaceAuthClient",
    "DSpaceClient", 
    "BatchItemCreator",
    
    # Concurrency control
    "ConcurrencyController",
    "ConcurrencyConfig",
    
    # Exceptions
    "DSpaceClientError",
    "AuthenticationError", 
    "DSpaceAPIError",
    "VersionIncompatibilityError",
]
