# Publishing Kinglet to PyPI

## Pre-release Checklist

✅ All tests pass (pytest)
✅ Critical features tested
✅ Documentation updated
✅ Version set in pyproject.toml
✅ Package structure verified

## TestPyPI Upload (Staging)

1. **Install build tools:**
```bash
pip install build twine
```

2. **Build package:**
```bash
python -m build
```

3. **Upload to TestPyPI:**
```bash
python -m twine upload --repository testpypi dist/*
```

4. **Test installation:**
```bash
pip install -i https://test.pypi.org/simple/ kinglet
python test_pypi_install.py
```

## Production PyPI Upload

Once TestPyPI works:

```bash
python -m twine upload dist/*
```

## Verification Commands

```bash
# Test imports
python -c "from kinglet import Kinglet, TestClient; print('✅ Import success')"

# Test basic functionality  
python test_critical_features.py

# Test PyPI simulation
python test_pypi_install.py
```

## Version Management

Update version in `pyproject.toml` before each release:
- Patch: 0.1.0 → 0.1.1 (bug fixes)
- Minor: 0.1.0 → 0.2.0 (new features)
- Major: 0.1.0 → 1.0.0 (breaking changes)

## Release Notes

For v0.1.0:
- ✅ Root path support (`/api` prefix)
- ✅ Typed query/path parameters (int, bool, UUID)
- ✅ Auth helpers (Bearer, Basic)
- ✅ Request ID tracking & CORS defaults
- ✅ Zero-dependency TestClient
- ✅ Cloudflare Workers compatibility
- ✅ 46 passing tests, 2 skipped (workers-specific)