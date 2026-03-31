# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **dspace_client.promo**: Optional **Atmire** session messaging — rotating messages with Rich (clickable URLs in supported terminals) after successful **`create_validated_client`** / **`connect_seed_client`**, and again when **`DSpaceAuthClient.close()`** runs (if a real HTTP client was closed). On an interactive TTY (and when **`CI`** is unset), closing the auth client may prompt to open **https://www.atmire.com/** in the default browser. Disable all promo output with **`DSPACE_CLIENT_DISABLE_ATMIRE_PROMO=1`**. Exported: **`show_atmire_promo_start`**, **`show_atmire_promo_end`**, **`is_atmire_promo_disabled`**.
- **BatchItemCreator** (`create_items_batch`): optional **`on_metrics_sample`** callback — invoked whenever batch progress metrics are printed (every 50 completed items and at the end), with `(completed, total, PerformanceMetrics)` for time-series / degradation reporting.
- **examples/seed** — **MegaSpace** (`megaspace.py`): declares **DSpace 9.0**; **`verify_server_version`** runs **by default** (use **`--skip-version-check`** to skip); **courtesy delay** between REST calls (prompt default 1.0 s, or **`--courtesy-delay`**); **slow-request** logging (threshold 2 s) with end-of-run table; **Rich** progress for sequential mega-bitstream uploads; optional **diagnostics export** to `YYYY-MM-DD-HH.MM-megaspace-{hostname}-raw.json` and `-readable.md` (UTC time in filename; payload includes config, samples, degradation hints); **`.gitignore`** patterns for those exports.
- **examples/seed** — **MiniSpace** / **`connect_seed_client`**: target **9.0**, version check on by default, **`--skip-version-check`**; **`connect_seed_client`** accepts **`courtesy_delay`** and **`slow_request_*`** passthrough to **`DSpaceClient`**.
- **dspace_client.auth**: Failure-only structured logging (`WARNING` / optional `DEBUG` on `dspace_client.auth`) for CSRF, JWT refresh, login, and verify failures.
- **tests**: `test_link_author_orcid_normalize.py`; auth tests for `refresh_jwt`, `ensure_session`, and CSRF cookie fallback.
- **.gitignore**: ignore `link_author_authorities_*.log` and `link_author_authorities_state.jsonl`.

### Fixed
- **DSpaceAuthClient**: Proactive session refresh prefers JWT refresh (`POST /authn/login` with `Authorization: Bearer` + `X-XSRF-TOKEN`) before full CSRF + password login, avoiding fragile `GET /security/csrf` on long runs when proxies strip `DSPACE-XSRF-TOKEN`. `ensure_session` treats “no prior auth” as `_last_auth_time is None` (not falsy `0.0`).
- **DSpaceAuthClient**: If `GET /security/csrf` omits the header, CSRF value may be taken from `DSPACE-XSRF-COOKIE` in the httpx jar.
- **examples/link_author_authorities**: ORCID mode — parse checksum `X`, `www.orcid.org` URLs, and vocabulary metadata `person.identifier.orcid` / `dc.identifier.uri`; resolve via vocabulary `entryID`, hyphenated + compact filters, then first-four-digit pagination; fetch entry detail only when list metadata lacks ORCID; dim progress during broad scan.

### Changed

- **examples/seed/megaspace.py**: **`--collections`** must be **at least 2** (argparse validation with a clear error). The full MegaSpace scenario assumes two collections (e.g. mega-metadata vs mega-bitstreams owning collections).
- **docs/API_GOTCHAS.md**: Notes on session refresh behavior and enabling auth diagnostics.

### Features
- **DSpaceAuthClient**: Complete authentication flow (CSRF → Login → JWT)
- **DSpaceClient**: Main API client with version validation
- **BatchItemCreator**: High-performance bulk operations
- **ConcurrencyController**: Adaptive concurrency control
- **RestContractFetcher**: Git-based documentation management
- **VersionCompatibility**: Multi-version compatibility checking

### API Coverage
- Communities (create, delete)
- Collections (create, delete)
- Items (create, delete)
- Bundles (create)
- Bitstreams (upload, delete)
- EPeople (create, delete, add to groups)
- Groups (create, delete, add subgroups)
- Collection default groups (item read, bitstream read)
- Statistics (view events)

### Documentation
- Comprehensive README with examples
- Quick start guide
- API reference
- Error handling guide
- Version compatibility documentation

### Examples
- Basic usage example
- Bulk import example
- Advanced authentication example

### Testing
- Unit tests for authentication
- Unit tests for core client
- Test fixtures and configuration
- Mock-based testing for HTTP operations

## [0.1.0] - 2024-01-XX

### Added
- Initial development release
- Core package structure
- Basic functionality implementation
- Documentation and examples
- Test suite foundation

### Technical Details
- Python 3.11+ support
- Async/await throughout
- Type hints for better IDE support
- Rich console output
- Git-based documentation fetching
- Version compatibility validation
- Comprehensive error handling
- Adaptive concurrency control
- Batch operations support
