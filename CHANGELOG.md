# Changelog

## 2.0.0 — Default-deny route security

### ⚠️ Breaking change: routes must declare their access posture

Kinglet now refuses, by default, to register a route that does not declare how
it is secured. This closes a class of authorization-bypass findings at the
framework level: a security decorator applied **above** a route decorator used
to leave the route silently unprotected (because the route registers and
dispatches exactly the callable it was given, and the later wrapper is never
seen). Rather than recover the wrapper by name — which reintroduces route
confusion — the framework now requires every route to be explicitly public or
explicitly protected, and fails closed otherwise.

At route registration (import time for module-level routes), a route is accepted
only if **one** of these holds:

1. It is declared public: `@app.get("/health", public=True)`.
2. Its handler carries a recognized access-control marker — set by a built-in
   auth decorator applied with the route decorator outermost, or by a custom
   decorator wrapped with the new `@security_decorator`.

Otherwise registration raises `RuntimeError` with guidance.

### Migration

For each route, do **one** of the following:

- **Public endpoint** (health, status, docs, public listings):
  ```python
  @app.get("/health", public=True)
  async def health(request): ...
  ```

- **Protected by a built-in decorator** — no change if already in the correct
  order (route decorator outermost):
  ```python
  @app.get("/admin")
  @require_auth
  async def admin(request): ...
  ```

- **Protected by your own decorator** — wrap it once with `@security_decorator`:
  ```python
  from kinglet import security_decorator

  @security_decorator
  def require_admin(handler):
      @functools.wraps(handler)
      async def wrapped(request): ...
      return wrapped
  ```

- **Authorize in middleware, or migrate later** — opt out per app:
  ```python
  app = Kinglet(enforce_route_policy=False)
  ```

> `validate_json_body` and `require_field` are validation, not access control;
> a route carrying only validation still needs `public=True` or real auth.

### Added

- `security_decorator` — make a custom security decorator recognized by the
  route policy (and fail fast in reversed order).
- `mark_secured` / `is_secured` — low-level helpers for the access-control marker.
- `public=True` keyword on all route decorators (`get`/`post`/`put`/`delete`/
  `patch`/`head`/`options`/`route`) on both `Kinglet` and `Router`.
- `enforce_route_policy` constructor flag on `Kinglet` and `Router` (default `True`).

### Notes

- Built-in auth/access decorators (`require_auth`, `require_owner`,
  `require_participant`, `require_claim`, `require_elevated_session`,
  `require_elevated_claim`, `allow_public_or_owner`, `require_dev`,
  `geo_restrict`) now mark their routes as secured automatically.
- Dispatch is unchanged: a route still executes exactly the callable registered
  at declaration time. No module/global name lookup, closure walking, or
  `__wrapped__` traversal is used to select handlers.
