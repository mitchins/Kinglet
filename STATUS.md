# Kinglet Project Status

This is the single source of truth for project roadmap and status.

## Framework Core

- 🟢 Decorator-based routing
- 🟢 Typed parameter extraction
- 🟢 Flexible middleware system
- 🟢 Auto error handling
- 🟢 Serverless testing (TestClient)

## Cloudflare Integration

- 🟢 D1 database helpers
- 🟢 R2 storage helpers
- 🟢 KV storage helpers
- 🟢 Environment-aware caching
- 🟢 D1-backed cache-aside pattern

## AWS Integration

- 🟢 SES email sending (zero JS required)

## ORM Features

- 🟢 Micro-ORM for D1
- 🟢 Field validation
- 🟢 Bulk operations
- 🟢 Schema generation CLI
- 🟢 Migration system
- 🟢 Custom primary keys
- 🟢 QuerySet with filtering

## Boilerplate Elimination (v1.7.0)

- 🟢 ServiceResult pattern
- 🟢 Model serialization framework
- 🟢 Pagination system (offset & cursor)
- 🟢 Input validation decorators

## Security

- 🟢 JWT validation
- 🟢 TOTP/2FA support
- 🟢 Geo-restrictions
- 🟢 Fine-grained auth decorators
- 🟢 Development environment security bypasses

## Testing Infrastructure

- 🟡 Centralized test fixtures (conftest.py)
    Phase 1 complete: d1_unwrap fixtures. Phase 2-3 pending.
- 🟡 Base test classes for ORM
    Standard patterns defined, migration in progress.

## Documentation

- 🟢 Core framework documentation
- 🟢 ORM guide with deployment strategies
- 🟢 Middleware guide
- 🟢 Caching guide
- 🟢 Security best practices
- 🟢 TOTP/2FA guide
- 🟢 Binary uploads guide

## API Documentation

- 🟢 OpenAPI 3.0 spec generation
- 🟢 Swagger UI / ReDoc serving

## Future Roadmap

- 🔵 Database migration helpers for field changes
- 🔵 WebSocket support
- 🟢 Full blown D1 mocking for downstream clients
    Mock D1 database for testing and development without Cloudflare infrastructure
    - MockD1Database with full Workers D1 API: prepare, bind, first, all, run, raw, batch, exec
    - D1Result with metadata (last_row_id, rows_read, rows_written, duration)
    - Proper type conversion (bool→int, None→NULL)
    - Compatible with kinglet ORM and d1_unwrap/d1_unwrap_results helpers
- 🟢 Full blown R2 mocking server for downstream clients
    Mock R2 object storage server for testing and development without Cloudflare infrastructure
    - MockR2Bucket with full Workers R2 API: head, get, put, delete, list
    - Range requests, conditional operations, multipart uploads
    - Compatible with kinglet storage helpers (r2_put, r2_get_content_info, etc.)

## Maintenance

- 🟢 90%+ test coverage across all features
- 🟢 CI/CD with GitHub Actions
- 🟢 SonarCloud quality gates
- 🟢 Codecov integration
- 🟢 Pre-commit hooks
