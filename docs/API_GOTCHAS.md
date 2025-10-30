# DSpace API Gotchas and Compatibility Notes

This document tracks important differences and compatibility issues between DSpace versions.

## Submitter Information

### DSpace 9+

Submitter information for items can be retrieved in multiple ways:

1. **Direct endpoint**: `GET /api/core/items/<uuid>/submitter`
2. **Embed parameter**: `GET /api/core/items/<uuid>?embed=submitter`

Example:
```python
# Direct endpoint
submitter = await client.get_item_submitter(item_uuid)

# Or via embed
response = await client.client.get(
    f"{client.base_url}/server/api/core/items/{item_uuid}?embed=submitter",
    headers={"Authorization": f"Bearer {client.jwt_token}"}
)
item_data = response.json()
submitter = item_data.get("_embedded", {}).get("submitter")
```

### DSpace 7

**The submitter endpoint does NOT exist in DSpace 7.**

The items API in DSpace 7 does not expose submitter information through:
- The `/submitter` endpoint (doesn't exist)
- The `?embed=submitter` parameter (submitter is not an exposed link)

**Workarounds for DSpace 7:**

1. Search workspaceitems with the submitter filter:
   ```
   GET /api/submission/workspaceitems/search/findBySubmitter?uuid=<submitter-uuid>
   ```

2. Access submission metadata during workflow stages (before items are archived)

3. Store submitter information in item metadata during submission

**Note:** The `get_item_submitter()` method in `dspace_client.core.DSpaceClient` will return `None` for DSpace 7 instances. This is expected behavior.

## Version Detection

The DSpaceClient can be configured with specific target versions:

```python
# Compatible with DSpace 9 only
client = DSpaceClient(base_url, jwt, csrf_token, http_client, target_versions="9.0")

# Compatible with DSpace 7.x
client = DSpaceClient(base_url, jwt, csrf_token, http_client, target_versions="7.6")

# Compatible with multiple versions
client = DSpaceClient(base_url, jwt, csrf_token, http_client, target_versions=["7.6", "8.0", "9.0"])
```

### Automatic Version Detection

You can also detect the DSpace version automatically at runtime:

```python
# Detect DSpace version by testing API capabilities
detected_version = await client.detect_dspace_version()

if detected_version:
    print(f"Detected DSpace version: {detected_version}")
    if detected_version.startswith("7."):
        print("DSpace 7 - some features may not be available")
    elif detected_version.startswith("9."):
        print("DSpace 9 - full feature support")
```

This is useful for scripts that need to conditionally enable features based on the DSpace version.

## Other Known Differences

### Embed Parameter Support

The `?embed=` parameter is supported in both DSpace 7 and 9, but the available embeds differ:

- **DSpace 7**: bundles, owningCollection, mappedCollections, templateItemOf, relationships, thumbnail
- **DSpace 9**: Same as DSpace 7, plus submitter

### Projections

Both DSpace 7 and 9 support projections:
- `?projection=full` - includes all linked subresources
- Default projection - excludes all subresource embeds

### Authentication

Authentication works identically across DSpace 7, 8, and 9:
- JWT tokens via `/api/authn/login`
- CSRF tokens via `DSPACE-XSRF-COOKIE` cookie
- Bearer token authentication for API calls

## References

- [DSpace 7 RestContract](https://github.com/DSpace/RestContract/tree/dspace-7_x)
- [DSpace 9 RestContract](https://github.com/DSpace/RestContract/tree/main)
- Local documentation: `docs/dspace-rest-api/7.6/` and `docs/dspace-rest-api/9.0/`
