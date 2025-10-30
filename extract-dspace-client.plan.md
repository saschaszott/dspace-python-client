# Extract DSpace Python Client Package

## Overview

Extract the generic DSpace REST API client from `dspace-seed` into a standalone Python package called `dspace-client` that can be:

- Installed via pip: `pip install dspace-client`
- Used as a base for any DSpace integration project
- Version-aware (supports DSpace 7.x, 8.x, 9.x)
- Self-documenting (fetches REST contract docs from GitHub)

## Phase 1: Core Package Structure

### Workspace Setup

**Current structure:**

```
dspace-python-client/
├── extract-dspace-client.plan.md    # This plan
└── dspace-seed/                     # Temporary - full copy of source project
    ├── dspace_seed/
    │   ├── client/                  # ← Extract these files
    │   ├── generators/
    │   └── scenarios/
    ├── API_GOTCHAS.md               # ← Copy this
    ├── requirements.txt             # ← Reference for dependencies
    └── ...
```

**Target structure (after execution):**

```
dspace-python-client/
├── dspace_client/                   # New package
│   ├── __init__.py
│   ├── auth.py
│   ├── core.py
│   ├── batch.py
│   ├── concurrency.py
│   ├── exceptions.py
│   ├── docs.py
│   └── version.py
├── examples/
├── docs/
├── tests/
├── pyproject.toml
├── requirements.txt
├── README.md
├── QUICKSTART.md
├── CHANGELOG.md
└── LICENSE
```

### Files to Extract from dspace-seed

**Core client modules** (keep all existing functionality):

- `dspace-seed/dspace_seed/client/auth.py` → `dspace_client/auth.py`
- `dspace-seed/dspace_seed/client/core.py` → `dspace_client/core.py`
- `dspace-seed/dspace_seed/client/batch.py` → `dspace_client/batch.py`
- `dspace-seed/dspace_seed/client/concurrency.py` → `dspace_client/concurrency.py`
- `dspace-seed/dspace_seed/client/__init__.py` → `dspace_client/__init__.py`

**Documentation to adapt**:

- `dspace-seed/API_GOTCHAS.md` → `docs/API_GOTCHAS.md` (update paths)
- Create new `README.md` - Focused on client usage, not seeding
- Create `QUICKSTART.md` - Simple examples

**Dependencies** (from dspace-seed/requirements.txt):

- httpx[http2]>=0.27.0 (HTTP client with cookie support)
- orjson>=3.10.0 (fast JSON)
- rich>=13.7.0 (console output - KEEP for better UX)
- tenacity>=8.2.0 (retry logic)
- pydantic>=2.0.0 (data validation - for future use)
- aiolimiter>=1.1.0 (rate limiting - for future use)

**NOT included** (dspace-seed specific):

- generators/ (Faker, seed packs - too specific)
- scenarios/ (minispace, megaspace - examples only)
- cli.py (dspace-seed CLI - not needed)
- seedpacks/ (deterministic data - not needed)

### New Package Structure

```
dspace-python-client/
├── dspace_client/
│   ├── __init__.py          # Main exports
│   ├── auth.py              # DSpaceAuthClient
│   ├── core.py              # DSpaceClient with all CRUD methods
│   ├── batch.py             # BatchItemCreator
│   ├── concurrency.py       # Adaptive concurrency control
│   ├── docs.py              # NEW: Documentation fetcher
│   ├── version.py           # NEW: Version compatibility helpers
│   └── exceptions.py        # NEW: Centralized exceptions
├── examples/
│   ├── basic_usage.py       # Simple create/read/delete
│   ├── bulk_import.py       # Batch operations
│   └── advanced_auth.py     # Session management
├── docs/
│   ├── README.md            # Points to fetched REST docs
│   ├── API_GOTCHAS.md       # Critical DSpace quirks
│   └── dspace-rest-api/     # Fetched docs (gitignored)
│       ├── v7.0/           # DSpace 7.x REST contract
│       ├── v8.0/           # DSpace 8.x REST contract
│       └── v9.0/           # DSpace 9.x REST contract
├── tests/                   # NEW: Unit tests
│   ├── test_auth.py
│   ├── test_core.py
│   └── conftest.py
├── pyproject.toml           # Package metadata
├── requirements.txt         # Dependencies
├── .gitignore              # Exclude fetched docs
├── README.md                # Main documentation
├── QUICKSTART.md            # Get started in 5 minutes
├── CHANGELOG.md             # Version history
└── LICENSE                  # GPL 3.0 license
```

## Phase 2: Smart Documentation System

### REST Contract Documentation Fetcher

Create `dspace_client/docs.py` with:

```python
class RestContractFetcher:
    """
    Manages DSpace REST API documentation with git-based updates.
    
    Uses git clone + fetch to keep docs fresh and track changes.
    """
    
    GITHUB_REPO = "DSpace/RestContract"
    GITHUB_URL = "https://github.com/DSpace/RestContract.git"
    # Store git repos in project directory (excluded from git)
    CACHE_DIR = Path("docs") / "dspace-rest-api"
    
    VERSION_MAPPING = {
        "bleeding-edge": "main",  # Latest development branch
        "7.0": "dspace-7.0",
        "7.1": "dspace-7.1", 
        "7.2": "dspace-7.2",
        "7.3": "dspace-7.3",
        "7.4": "dspace-7.4",
        "7.5": "dspace-7.5",
        "7.6": "dspace-7.6",
        "8.0": "dspace-8.0",
        "9.0": "main",  # DSpace 9 is on main
    }
    
    async def fetch_version(self, version: str, force_update: bool = False) -> Path:
        """
        Clone/fetch REST contract for specific DSpace version.
        
        CALLED AUTOMATICALLY on DSpaceClient initialization.
        
        Args:
            version: "bleeding-edge", "7.0", "8.0", "9.0", etc.
            force_update: Force git fetch even if recently updated
        
        Returns:
            Path to git repository directory
        
        Raises:
            ValueError: If version is not supported
            NetworkError: If GitHub is unreachable
        """
        # STEP 1: Check if git repo exists
        # STEP 2: If not, git clone the repository
        # STEP 3: If exists, git fetch to get latest changes
        # STEP 4: Checkout the correct branch/tag
        # STEP 5: Show progress with Rich progress bar
        # STEP 6: Return path to repo directory
    
    async def update_all_versions(self) -> Dict[str, bool]:
        """
        Update all cached versions with latest changes.
        
        Returns:
            Dict mapping version to success status
        """
        # Git fetch for all cached versions
        # Show progress with Rich
        # Return update status for each version
    
    def get_last_update_time(self, version: str) -> Optional[datetime]:
        """Get timestamp of last successful update for version."""
    
    def should_update(self, version: str, max_age_hours: int = 24) -> bool:
        """Check if version needs updating based on age."""
    
    def list_cached_versions(self) -> List[str]:
        """List locally cached documentation versions."""
    
    def get_endpoint_docs(self, endpoint: str, version: str) -> str:
        """Get documentation for specific endpoint from git repo."""
    
    def validate_operation(self, operation: str, endpoint: str, versions: List[str]) -> bool:
        """
        Validate if operation is supported across all target versions.
        
        Returns True if compatible with ALL versions, False otherwise.
        """
```

**Documentation Structure (Git-based):**
```
docs/
├── README.md                    # Points to fetched REST docs
├── API_GOTCHAS.md              # Critical DSpace quirks
└── dspace-rest-api/            # Git repositories (gitignored)
    ├── bleeding-edge/          # Git repo: main branch (auto-updated)
    ├── v7.0/                   # Git repo: dspace-7.0 branch
    ├── v7.6/                   # Git repo: dspace-7.6 branch
    ├── v8.0/                   # Git repo: dspace-8.0 branch
    └── v9.0/                   # Git repo: main branch
```

**Git-based Update Strategy:**
When a user creates a `DSpaceClient` instance:
1. User specifies `target_versions="bleeding-edge"` (default) or `["7.6", "8.0", "9.0"]`
2. Client checks if git repo exists in `docs/dspace-rest-api/{version}/`
3. If not cloned, git clone the RestContract repository
4. If exists, git fetch to get latest changes (if older than 24h)
5. Checkout the correct branch/tag for the version
6. Show progress with Rich progress bar
7. Load compatibility rules for validation
8. All subsequent API calls are validated against target version(s)

**Automatic Updates:**
- Check last update time before each client initialization
- Auto-fetch if docs are older than 24 hours (configurable)
- Background updates for bleeding-edge (most active branch)
- Manual update via CLI: `dspace-docs update`

**Create .gitignore file:**
```
# Fetched DSpace REST API documentation
docs/dspace-rest-api/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

### CLI Tool for Documentation

Add optional CLI (via `[cli]` extra):

```bash
# Update all cached versions with latest changes
dspace-docs update

# Update specific version
dspace-docs update 9.0

# Force update (ignore age check)
dspace-docs update --force

# List available versions and their last update time
dspace-docs list

# Search for endpoint documentation
dspace-docs search "communities"

# Compare endpoint across versions
dspace-docs diff "communities" --versions 7.0,8.0,9.0

# Show git status for all versions
dspace-docs status

# Clean up old/unused versions
dspace-docs cleanup
```

**Background Update Service (Optional):**
```bash
# Start background service to keep docs fresh
dspace-docs daemon --interval 6h

# Check for updates without downloading
dspace-docs check-updates
```

## Phase 3: Version Compatibility System

### Version Awareness

Create `dspace_client/version.py`:

```python
@dataclass
class DSpaceVersion:
    major: int
    minor: int
    
    SUPPORTED = {
        "7.0": ["7.0", "7.1", "7.2", "7.3", "7.4", "7.5", "7.6"],
        "8.0": ["8.0"],
        "9.0": ["9.0"],
    }
    
class VersionCompatibility:
    """
    Validates API operations against target DSpace version(s).
    
    CRITICAL: Every API call is validated before execution.
    """
    
    def __init__(self, target_versions: List[str], docs_fetcher: RestContractFetcher):
        """
        Initialize validator with target versions.
        
        Args:
            target_versions: List of versions to validate against
            docs_fetcher: Fetcher with loaded REST contract docs
        """
        self.target_versions = target_versions
        self.docs_fetcher = docs_fetcher
    
    def validate_before_call(self, method_name: str, endpoint: str, operation: str) -> None:
        """
        Validate operation is compatible with ALL target versions.
        
        Called automatically before every API call.
        
        Raises:
            VersionIncompatibilityError: If operation not supported in any target version
        
        Example:
            validator.validate_before_call(
                "create_community",
                "/api/core/communities",
                "POST"
            )
        """
        # Check operation against all target versions
        # Raise error if incompatible with ANY version
        # Log warning if using deprecated features
    
    def get_compatibility_report(self) -> Dict[str, List[str]]:
        """Generate report of which operations work with which versions."""
```

### Enhanced Client Initialization

**CRITICAL: Version-First Design**

Users MUST specify target DSpace version(s) at initialization. This is required for:
1. Fetching correct REST API documentation
2. Validating every API call against the target version(s)
3. Preventing incompatible operations

```python
class DSpaceClient:
    def __init__(
        self,
        base_url: str,
        jwt_token: str,
        csrf_token: str,
        http_client: httpx.AsyncClient,
        target_versions: Union[str, List[str]] = "bleeding-edge",  # REQUIRED
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize DSpace client with version compatibility checking.
        
        Args:
            target_versions: DSpace version(s) to be compatible with.
                - "bleeding-edge" (default): Latest main branch from RestContract
                - "7.0", "8.0", "9.0": Specific stable versions
                - ["7.6", "8.0", "9.0"]: Multiple versions (validates against ALL)
        
        On initialization:
        1. Validates target_versions parameter
        2. Checks if git repos exist for target version(s)
        3. If not cloned, git clone RestContract repository
        4. If exists, git fetch latest changes (if older than 24h)
        5. Checkout correct branch/tag for each version
        6. Loads compatibility rules for validation
        7. Sets up automatic update checking
        """
        # Fetch docs immediately on init
        # Load version compatibility rules
        # Set up validation for all subsequent API calls
```

**Version Options:**
- `"bleeding-edge"` - Latest development (main branch)
- `"7.0"`, `"7.1"`, ..., `"7.6"` - DSpace 7.x releases
- `"8.0"` - DSpace 8.x
- `"9.0"` - DSpace 9.x
- `["7.6", "8.0", "9.0"]` - Multi-version compatibility (strictest validation)

## Phase 4: Runtime Validation System

### Validation Workflow

**Every API call is validated before execution:**

```python
# In DSpaceClient
async def create_community(self, name: str, metadata: dict = None) -> dict:
    """Create a new community."""
    
    # STEP 1: Validate operation against target versions
    self.validator.validate_before_call(
        method_name="create_community",
        endpoint="/api/core/communities",
        operation="POST"
    )
    # Raises VersionIncompatibilityError if not supported
    
    # STEP 2: Execute the API call
    response = await self._request("POST", "/api/core/communities", json=data)
    
    return response
```

### Validation Rules

**Multi-version compatibility:**
- If `target_versions=["7.6", "8.0", "9.0"]`, operation must work in ALL three versions
- If ANY version doesn't support the operation, raise error BEFORE making the call
- This prevents runtime failures and ensures cross-version compatibility

**Validation sources:**
1. Fetched REST contract documentation
2. Known endpoint patterns from docs
3. HTTP method availability (GET, POST, PUT, DELETE, PATCH)
4. Required/optional parameters per version

**User feedback:**
```
✗ Error: create_workflow_item() not supported in DSpace 7.6
  Target versions: ['7.6', '8.0', '9.0']
  Supported in: ['8.0', '9.0']
  Missing in: ['7.6']
  
  Suggestion: Use target_versions=['8.0', '9.0'] or implement workaround for 7.6
```

## Phase 5: Additional Implementation Details

### Core Client Methods with Validation

Every method in `DSpaceClient` follows this pattern:

```python
async def create_item(self, collection_uuid: str, metadata: dict) -> dict:
    """Create item in collection."""
    # Validate first
    self.validator.validate_before_call("create_item", "/api/core/items", "POST")
    # Then execute
    return await self._request("POST", "/api/core/items", ...)

async def upload_bitstream(self, bundle_uuid: str, file_path: Path) -> dict:
    """Upload bitstream to bundle."""
    # Validate first
    self.validator.validate_before_call("upload_bitstream", "/api/core/bitstreams", "POST")
    # Then execute
    return await self._upload_file(...)
```

All existing methods from `dspace-seed/dspace_seed/client/core.py` will be wrapped with validation.

## Phase 6: Code Improvements

### Centralize Exceptions

Create `dspace_client/exceptions.py`:

```python
class DSpaceClientError(Exception):
    """Base exception for all client errors."""

class AuthenticationError(DSpaceClientError):
    """Authentication failed."""

class DSpaceAPIError(DSpaceClientError):
    """API request failed."""
    
class VersionIncompatibilityError(DSpaceClientError):
    """Method not compatible with target DSpace version."""
```

Move existing exceptions from auth.py and core.py here.

### Improve Type Hints

Add comprehensive type hints throughout:

- Use `typing.TypedDict` for response objects
- Add return type hints to all methods
- Consider using `pydantic` models for complex responses

### Rich Console Output

Keep using Rich for beautiful console output:

```python
from rich.console import Console

console = Console()

# Rich provides:
# - Beautiful progress bars
# - Colored output
# - Tables and formatting
# - Better UX than standard logging
```

Note: Users who want standard logging can still configure Python's logging module separately.

## Phase 7: Examples & Documentation

### Example Scripts

**examples/basic_usage.py** - Simple CRUD:

```python
"""Basic DSpace client usage example."""
import asyncio
from dspace_client import DSpaceAuthClient, DSpaceClient

async def main():
    # Authenticate
    auth = DSpaceAuthClient("https://demo.dspace.org")
    jwt, status = await auth.authenticate("user", "pass")
    
    # Create client with version specification (REQUIRED)
    # Default is "bleeding-edge" - latest development
    client = DSpaceClient(
        base_url="https://demo.dspace.org",
        jwt_token=jwt,
        csrf_token=auth.csrf_token,
        http_client=auth.client,
        target_versions="bleeding-edge",  # or ["7.6", "8.0", "9.0"]
    )
    # On first run, this will fetch REST API docs from GitHub
    # Subsequent runs use cached docs
    
    # Create a community (validated against target versions)
    community = await client.create_community("My Community")
    print(f"Created: {community['uuid']}")
    
    # Clean up
    await client.delete_community(community['uuid'])
    await auth.close()

if __name__ == "__main__":
    asyncio.run(main())
```

**examples/bulk_import.py** - Batch operations with concurrency

**examples/advanced_auth.py** - Session management, re-authentication

### Documentation Files

**README.md** - Main entry point:

- What is dspace-client?
- Installation instructions
- Quick example
- Link to full documentation
- Link to DSpace REST API docs

**QUICKSTART.md** - Get running in 5 minutes:

- Install package
- Authenticate
- Create your first community
- Where to go next

**API_GOTCHAS.md** - Keep from dspace-seed, update paths

## Phase 8: Testing & Quality

### Unit Tests

Create comprehensive test suite:

- `tests/test_auth.py` - Authentication flow
- `tests/test_core.py` - CRUD operations
- `tests/test_batch.py` - Batch operations
- `tests/test_concurrency.py` - Concurrency control
- `tests/test_version.py` - Version compatibility

Use `pytest` + `pytest-asyncio` + `respx` (HTTP mocking)

### Package Configuration

**pyproject.toml**:

```toml
[project]
name = "dspace-client"
version = "0.1.0"
description = "Python client for DSpace REST API (v7, v8, v9)"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "GPL-3.0-or-later"}
authors = [
    {name = "Bram Luyten", email = "bram@atmire.com"}
]
keywords = ["dspace", "rest-api", "client", "repository"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]

dependencies = [
    "httpx[http2]>=0.27.0",
    "orjson>=3.10.0",
    "rich>=13.7.0",
    "tenacity>=8.2.0",
    "gitpython>=3.1.0",  # For git operations
]

[project.optional-dependencies]
cli = ["typer>=0.12.0"]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]

[project.urls]
Homepage = "https://github.com/yourusername/dspace-python-client"
Documentation = "https://github.com/yourusername/dspace-python-client#readme"
Repository = "https://github.com/yourusername/dspace-python-client"
"Bug Tracker" = "https://github.com/yourusername/dspace-python-client/issues"
"DSpace REST Contract" = "https://github.com/DSpace/RestContract"

[project.scripts]
dspace-docs = "dspace_client.docs:cli_main"
```

## Phase 9: Local Installation & Verification

### Development Installation

1. Install package in editable mode: `pip install -e .`
2. Test imports work: `from dspace_client import DSpaceAuthClient, DSpaceClient`
3. Run examples against demo.dspace.org
4. Verify all functionality works

### Future Work (Not in Initial Build)

**GitHub Repository Setup:**

- Create new repo: `dspace-python-client`
- Add comprehensive README
- Set up GitHub Actions (tests, linting, building)

**PyPI Publishing** (when ready for public release):

- Build package: `python -m build`
- Test on TestPyPI first
- Publish to PyPI: `twine upload dist/*`
- Users can install: `pip install dspace-client`

**Versioning Strategy:**

- Use semantic versioning
- `0.1.0` - Initial development release
- `1.0.0` - First stable public release

## Key Design Decisions

### Version-First Architecture (CRITICAL)

**The most important design decision:**

1. **Mandatory version specification**: Users MUST specify target DSpace version(s) at client initialization
2. **Automatic documentation fetching**: REST API docs are fetched immediately on first init
3. **Pre-execution validation**: Every API call is validated against target versions BEFORE execution
4. **Multi-version compatibility**: When targeting multiple versions, ALL must support the operation
5. **Clear error messages**: Users get actionable feedback about version incompatibilities

**Why this matters:**
- Prevents runtime failures from version incompatibilities
- Enables building applications that work across multiple DSpace versions
- Provides early feedback during development
- Documents which DSpace versions are supported by the implementation

**Default behavior:**
```python
# Default to bleeding-edge (latest development)
client = DSpaceClient(..., target_versions="bleeding-edge")
# First run: Git clone RestContract repo, checkout main branch
# Subsequent runs: Git fetch if older than 24h, checkout main branch
# Always: Load latest docs for validation
```

**Update Workflow:**
1. **First initialization**: Git clone RestContract repository
2. **Subsequent initializations**: Check last update time
3. **Auto-update**: If docs older than 24h, run `git fetch` + `git checkout`
4. **Manual update**: Use `dspace-docs update` CLI command
5. **Background service**: Optional daemon to keep docs fresh
6. **Validation**: All API calls validated against latest docs

### What Makes This Generic vs dspace-seed?

**dspace-seed** (specific use case):

- Deterministic content generation
- Science-themed data
- Seed packs with famous publications
- CLI for running scenarios
- Faker integration

**dspace-client** (generic library):

- Pure API client
- No content generation
- No CLI (except docs tool)
- Users bring their own data
- Reusable in any Python project

### Modularity Strategy

The package can be used at different levels:

**Level 1 - Just Auth:**

```python
from dspace_client import DSpaceAuthClient
auth = DSpaceAuthClient(url)
jwt, status = await auth.authenticate(user, pass)
# Use jwt with your own HTTP requests
```

**Level 2 - Basic Client:**

```python
from dspace_client import DSpaceAuthClient, DSpaceClient
# Use built-in CRUD methods
```

**Level 3 - Batch Operations:**

```python
from dspace_client import BatchItemCreator, ConcurrencyConfig
# High-performance bulk operations
```

### Extension Points

Users can extend the client:

```python
class MyDSpaceClient(DSpaceClient):
    async def create_custom_workflow(self):
        # Add your own methods
        pass
```

## Success Criteria

- ✅ Package installs cleanly via pip
- ✅ All authentication flows work (CSRF, JWT, session management)
- ✅ All CRUD operations work (communities, collections, items, etc.)
- ✅ **Version-first initialization**: Users must specify target versions
- ✅ **Automatic doc fetching**: REST API docs fetched on first init with progress bar
- ✅ **Git-based updates**: Uses git clone/fetch to keep docs fresh
- ✅ **Auto-update checking**: Checks for updates if docs older than 24h
- ✅ **Pre-execution validation**: Every API call validated before execution
- ✅ **Multi-version support**: Can target single or multiple DSpace versions
- ✅ **"bleeding-edge" default**: Defaults to latest main branch
- ✅ **CLI update tools**: `dspace-docs update`, `dspace-docs status`, etc.
- ✅ Documentation fetcher works for DSpace 7.x, 8.0, 9.0, bleeding-edge
- ✅ Examples run successfully against demo.dspace.org
- ✅ Tests pass with >80% coverage
- ✅ Can be used in other projects without modification
- ✅ Clear error messages for version incompatibilities

## Future Enhancements (Not in Initial Release)

- Add more REST endpoints (search, browse, workflows, etc.)
- Sync (non-async) wrapper for simpler use cases
- Response object models using Pydantic
- Automatic retry with exponential backoff (already partially there)
- Rate limiting integration
- Connection pooling optimization
- GraphQL support (if DSpace adds it)