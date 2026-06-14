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
  `require_elevated_claim`, `allow_public_or_owner`, `require_dev`) now mark
  their routes as secured automatically.
- **`geo_restrict` does NOT satisfy the policy.** It reads the forgeable
  `CF-IPCountry` hint and fails open in production, so it is a supplementary
  filter, not an identity posture. A geo-restricted route needs `public=True`
  or a real auth decorator. (`require_dev` fails closed → 404 in production, so
  it does count.)
- Disabling the policy (`enforce_route_policy=False`) emits a
  `RoutePolicyWarning` so an intentional opt-out is not mistaken for one
  forgotten during migration.
- The "secured" posture is tracked by **object identity** in an internal weak
  registry, set via `mark_secured()` / `@security_decorator`. There is no public
  `__kinglet_secured__` attribute: hand-setting that attribute does nothing
  (use `mark_secured()`), and it cannot be laundered onto an outer wrapper by
  `functools.wraps`. The route-registered order guard uses a single weak
  registry keyed by **logical identity**: `id()` for ordinary callables, and
  `(id(instance), id(function))` for bound methods, so a *fresh* `obj.method` access of
  a registered bound method is still recognized and the reversed-order guard
  still fires. It also tracks unhashable callable handlers, and is not copied by
  `functools.wraps`. (The secured marker deliberately stays strict-`id` only:
  logical/value equality there would let a value-equal callable launder the auth
  posture.)
- **Residual order-guard limitation (by design).** A handler that is not
  weakref-able (e.g. `__slots__` without `__weakref__`) cannot be tracked at
  all; Kinglet warns (`RoutePolicyWarning`) at registration. This is **not** a
  default-config risk (the default policy refuses an unsecured route before it
  registers); it only matters under `enforce_route_policy=False` with a reversed
  security decorator. Teams that want such cases to fail rather than warn should
  treat `RoutePolicyWarning` as an error in CI:
  `warnings.filterwarnings("error", category=RoutePolicyWarning)`.
- `Kinglet` now also exposes `head()` and `options()` route decorators (were
  previously only on `Router`).
- The registration error names the offending handler and points at
  `@security_decorator`.
- Dispatch is unchanged: a route still executes exactly the callable registered
  at declaration time. No module/global name lookup, closure walking, or
  `__wrapped__` traversal is used to select handlers.
