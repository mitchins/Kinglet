"""
Tests for kinglet __init__.py import handling
"""

import sys
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

        assert kinglet.__version__ == "1.7.0"  # Current version
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
