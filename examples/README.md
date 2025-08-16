# Kinglet Examples

## Fine-Grained Authorization (v1.4.0)

```bash
python examples/authz_example.py
```

Shows:
- **JWT authentication**: HS256 token validation with Cloudflare Access fallback
- **Public/private resources**: `@allow_public_or_owner` for visibility control
- **Owner-only operations**: `@require_owner` with admin override
- **Participant access**: `@require_participant` for multi-user resources
- **Admin override**: Emergency access via `ADMIN_IDS` environment variable
- **R2 media ownership**: Store owner metadata for access control

**Admin Override Pattern:**
```python
@require_owner(load_resource, allow_admin_env="ADMIN_IDS")
async def delete_post(req, obj):
    # Owner OR admin can delete
```

Set admins in `wrangler.toml`:
```toml
[vars]
ADMIN_IDS = "admin-1,admin-2,support-3"  # Comma-separated user IDs
```

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

## R2 Media Example

```bash
# See r2_media_example.py
```

Shows how to serve binary files from Cloudflare R2 storage with the critical technique:

```python
# ✅ Correct: Return R2 stream to WorkersResponse  
return WorkersResponse(obj.body, status=200, headers=headers)

# ❌ Wrong: Converting to bytes causes TypeError
return WorkersResponse(bytes_data, status=200, headers=headers)  # FAILS
```

**Key insight**: `obj.body` is a ReadableStream that Workers can pipe directly to clients. Kinglet detects `WorkersResponse` and bypasses all processing, enabling efficient binary streaming.

## Cloudflare Workers Demo

See [CloudFlare-Demo/](../CloudFlare-Demo/) for a complete Cloudflare Workers deployment example with:
- Project structure
- Configuration files
- Deployment instructions