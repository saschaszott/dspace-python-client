# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of DSpace Python client
- Version-first initialization with automatic documentation fetching
- Pre-execution validation for all API operations
- Multi-version compatibility support (DSpace 7.x, 8.x, 9.x)
- Git-based documentation management with auto-updates
- Rich console output for beautiful user experience
- Batch operations with adaptive concurrency control
- Comprehensive error handling with actionable messages

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
