"""Single source of truth for supported DSpace versions and RestContract branches."""

from typing import Dict, List

# Keys accepted as target_versions / docs fetch version arguments.
SUPPORTED_VERSIONS: Dict[str, List[str]] = {
    "bleeding-edge": ["bleeding-edge"],
    "7.0": ["7.0", "7.1", "7.2", "7.3", "7.4", "7.5", "7.6"],
    "7.1": ["7.1", "7.2", "7.3", "7.4", "7.5", "7.6"],
    "7.2": ["7.2", "7.3", "7.4", "7.5", "7.6"],
    "7.3": ["7.3", "7.4", "7.5", "7.6"],
    "7.4": ["7.4", "7.5", "7.6"],
    "7.5": ["7.5", "7.6"],
    "7.6": ["7.6"],
    "8.0": ["8.0"],
    "9.0": ["9.0"],
}

# RestContract git branch/tag per version key.
REST_CONTRACT_BRANCHES: Dict[str, str] = {
    "bleeding-edge": "main",
    "7.0": "dspace-7_x",
    "7.1": "dspace-7_x",
    "7.2": "dspace-7_x",
    "7.3": "dspace-7_x",
    "7.4": "dspace-7_x",
    "7.5": "dspace-7_x",
    "7.6": "dspace-7_x",
    "8.0": "dspace-8.0",
    "9.0": "main",
}

DEFAULT_CACHE_DIR_NAME = "dspace-rest-api"
