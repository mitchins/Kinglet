# Kinglet Examples

## Basic API Example

```bash
python examples/basic_api.py
```

Shows:
- Routing with root paths
- Typed query and path parameters
- Authentication helpers (Bearer tokens)
- Request validation
- Zero-dependency testing with TestClient

## Decorators Example

```bash
python examples/decorators_example.py
```

Shows:
- **Exception wrapping**: Automatic error handling with detailed responses
- **Dev-only endpoints**: Restrict access to development environments
- **Geo-restrictions**: Block/allow access based on country
- **Decorator combinations**: Chain multiple restrictions together
- **Global vs manual wrapping**: Configure exception handling app-wide or per-endpoint

## Cloudflare Workers Demo

See [CloudFlare-Demo/](../CloudFlare-Demo/) for a complete Cloudflare Workers deployment example with:
- Project structure
- Configuration files
- Deployment instructions