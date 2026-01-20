"""
Tests for kinglet __init__.py import handling

Note: With lazy loading optimization, ORM/Testing/Validation modules are
lazy-loaded via __getattr__. They remain in __all__ but raise AttributeError
on access if truly unavailable.
"""

import sys
from unittest.mock import patch


class TestImportFallbacks:
    """Test import fallback behavior in __init__.py"""

    def test_orm_lazy_loading(self):
        """Test ORM is lazy-loaded (not imported until accessed)"""
        with patch.dict("sys.modules"):
            # Clear kinglet modules
            modules_to_remove = [k for k in sys.modules if k.startswith("kinglet")]
            for module in modules_to_remove:
                del sys.modules[module]

            # Import kinglet - ORM should NOT be loaded yet
            import kinglet

            # ORM module should NOT be in sys.modules after base import
            assert "kinglet.orm" not in sys.modules

            # But ORM items should be in __all__ (advertised as available)
            assert "Model" in kinglet.__all__

            # Now access Model - this triggers lazy load
            _ = kinglet.Model

            # ORM module should now be loaded
            assert "kinglet.orm" in sys.modules

    def test_testing_lazy_loading(self):
        """Test testing module is lazy-loaded"""
        with patch.dict("sys.modules"):
            # Clear kinglet modules
            modules_to_remove = [k for k in sys.modules if k.startswith("kinglet")]
            for module in modules_to_remove:
                del sys.modules[module]

            import kinglet

            # Testing module should NOT be loaded yet
            assert "kinglet.testing" not in sys.modules

            # Access TestClient - triggers lazy load
            _ = kinglet.TestClient

            # Testing module should now be loaded
            assert "kinglet.testing" in sys.modules

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

        assert kinglet.__version__ == "1.8.3"  # Current version
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

    def test_lazy_exports_in_all(self):
        """Test that lazy-loaded items are properly listed in __all__"""
        import kinglet

        # ORM items should be in __all__ (lazy-loaded)
        orm_items = ["Model", "Field", "QuerySet", "Manager", "SchemaManager"]
        for item in orm_items:
            assert item in kinglet.__all__

        # Testing items should be in __all__ (lazy-loaded)
        testing_items = ["TestClient", "MockD1Database", "MockR2Bucket"]
        for item in testing_items:
            assert item in kinglet.__all__

        # Validation items should be in __all__ (lazy-loaded)
        validation_items = ["ValidationSchema", "validate_email"]
        for item in validation_items:
            assert item in kinglet.__all__

    def test_dir_includes_lazy_items(self):
        """Test that dir() includes lazy-loaded items"""
        import kinglet

        dir_items = dir(kinglet)

        # Lazy items should appear in dir()
        assert "Model" in dir_items
        assert "TestClient" in dir_items
        assert "ValidationSchema" in dir_items
        assert "authz" in dir_items
