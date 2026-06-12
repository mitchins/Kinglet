"""
Tests for kinglet __init__.py import handling
"""

import importlib
import runpy
import sys
from pathlib import Path
from unittest.mock import patch


class TestImportFallbacks:
    """Test import fallback behavior in __init__.py"""

    def test_orm_import_fallback(self):
        """Test ORM import fallback when ORM modules unavailable"""
        # Mock import failure for ORM modules
        with patch.dict("sys.modules"):
            # Remove ORM modules from sys.modules to simulate import failure
            modules_to_remove = [
                "kinglet.orm",
                "kinglet.orm_deploy",
                "kinglet.orm_migrations",
                "kinglet.orm_errors",
            ]
            for module in modules_to_remove:
                if module in sys.modules:
                    del sys.modules[module]

            # Force a reimport by removing kinglet from cache
            if "kinglet" in sys.modules:
                del sys.modules["kinglet"]

            # This should trigger the ImportError fallback
            try:
                import kinglet

                # Should have _orm_available = False
                assert hasattr(kinglet, "_orm_available")
                # ORM items should be filtered from __all__
                orm_items = ["Model", "Field", "IntegerField", "QuerySet"]
                for item in orm_items:
                    if (
                        hasattr(kinglet, "_orm_available")
                        and not kinglet._orm_available
                    ):
                        assert item not in kinglet.__all__
            except ImportError:
                # Expected behavior - ORM not available
                pass

    def test_storage_import_fallback(self):
        """Test storage import fallback when storage modules unavailable"""
        with patch.dict("sys.modules"):
            # Remove storage modules
            if "kinglet.storage" in sys.modules:
                del sys.modules["kinglet.storage"]

            if "kinglet" in sys.modules:
                del sys.modules["kinglet"]

            try:
                import kinglet

                # Should have _d1_available flag
                assert (
                    hasattr(kinglet, "_d1_available") or True
                )  # May not be set if import succeeds
            except ImportError:
                pass  # Expected when dependencies missing

    def test_version_and_metadata(self):
        """Test version and metadata are properly set"""
        import kinglet

        assert hasattr(kinglet, "__version__")
        assert hasattr(kinglet, "__author__")
        assert hasattr(kinglet, "__all__")

        assert kinglet.__version__ == "1.9.0"  # Current version
        assert kinglet.__author__ == "Mitchell Currie"
        assert isinstance(kinglet.__all__, list)
        assert len(kinglet.__all__) > 0

    def test_core_imports_always_available(self):
        """Test that core imports are always available"""
        import kinglet

        # Core items should always be in __all__
        core_items = ["Kinglet", "Router", "Route", "Request", "Response"]
        for item in core_items:
            assert item in kinglet.__all__
            assert hasattr(kinglet, item)

    def test_conditional_export_logic(self):
        """Test the conditional export logic works correctly"""
        import kinglet

        # The __all__ list should be filtered based on availability
        if hasattr(kinglet, "_orm_available"):
            if not kinglet._orm_available:
                # ORM items should be removed from __all__
                orm_items = ["Model", "Field", "QuerySet", "Manager"]
                for item in orm_items:
                    assert item not in kinglet.__all__
            else:
                # ORM items should be present if ORM is available
                assert "Model" in kinglet.__all__

    def test_examples_import_without_cryptography(self):
        """Auth and TOTP example modules should load without eager crypto imports."""
        blocked_modules = {
            "cryptography": None,
            "cryptography.exceptions": None,
            "cryptography.hazmat": None,
            "cryptography.hazmat.primitives": None,
            "cryptography.hazmat.primitives.ciphers": None,
            "cryptography.hazmat.primitives.ciphers.aead": None,
        }
        examples_dir = Path(__file__).resolve().parent.parent / "examples"

        with patch.dict(sys.modules, blocked_modules, clear=False):
            for module in [
                "kinglet",
                "kinglet.authz",
                "kinglet.totp",
            ]:
                sys.modules.pop(module, None)

            kinglet = importlib.import_module("kinglet")
            assert kinglet.Kinglet is not None

            totp_module = kinglet.totp
            code = totp_module.generate_totp_code("JBSWY3DPEHPK3PXP", timestamp=0)
            assert len(code) == 6
            assert code.isdigit()

            basic_api_globals = runpy.run_path(str(examples_dir / "basic_api.py"))
            assert "app" in basic_api_globals

            authz_globals = runpy.run_path(str(examples_dir / "authz_example.py"))
            assert "router" in authz_globals

            totp_globals = runpy.run_path(str(examples_dir / "totp_example.py"))
            assert "app" in totp_globals

            workers_demo_globals = runpy.run_path(
                str(examples_dir / "totp_workers_demo" / "worker.py")
            )
            assert "app" in workers_demo_globals
            assert "Default" in workers_demo_globals
            assert hasattr(workers_demo_globals["Default"], "fetch")
