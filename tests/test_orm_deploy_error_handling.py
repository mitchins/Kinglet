"""
Tests for ORM deployment error handling
"""

import json
from unittest.mock import Mock, mock_open, patch

import pytest

from kinglet.orm_deploy import (
    deploy_schema,
    generate_lock,
    generate_migrations,
    generate_schema,
    import_models,
    verify_schema,
)


class TestImportModelsErrorHandling:
    """Test model import error handling"""

    def test_import_nonexistent_module(self):
        """Test importing a non-existent module raises ImportError"""
        with pytest.raises(ImportError):
            import_models("nonexistent.module.path")

    def test_import_module_with_no_models(self):
        """Test importing module with no Model classes returns empty list"""
        with patch("importlib.import_module") as mock_import:
            # Create a simpler mock module without mocking builtins
            mock_module = Mock()

            # Set attributes directly on the mock module
            mock_module.some_function = lambda: None
            mock_module.CONSTANT = 42
            mock_module.NotAModel = Mock()  # Not a Model subclass

            # Configure the mock to return these attributes when dir() is called
            mock_module.__dir__ = Mock(
                return_value=["some_function", "CONSTANT", "NotAModel"]
            )

            mock_import.return_value = mock_module

            models = import_models("empty.module")
            assert models == []


class TestGenerateSchemaErrorHandling:
    """Test schema generation error handling"""

    def test_generate_schema_no_models_warning(self):
        """Test generate_schema with no models prints warning and returns empty"""
        with patch("kinglet.orm_deploy.import_models", return_value=[]):
            with patch("builtins.print") as mock_print:
                result = generate_schema("empty.module")

                assert result == ""
                # Should print warning to stderr
                mock_print.assert_called_once()
                call_args = mock_print.call_args
                assert "Warning" in call_args[0][0]
                assert "empty.module" in call_args[0][0]


class TestGenerateLockErrorHandling:
    """Test lock file generation error handling"""

    def test_generate_lock_no_models(self):
        """Test generate_lock returns 1 when no models found"""
        with patch("kinglet.orm_deploy.import_models", return_value=[]):
            with patch("builtins.print"):
                result = generate_lock("empty.module")
                assert result == 1

    def test_generate_lock_file_write_error(self):
        """Test generate_lock handles file write errors"""
        # Mock successful model import
        mock_model = Mock()
        mock_model._meta.table_name = "test_table"

        with patch("kinglet.orm_deploy.import_models", return_value=[mock_model]):
            with patch(
                "kinglet.orm_migrations.SchemaLock.generate_lock",
                return_value={"test": "data"},
            ):
                with patch(
                    "kinglet.orm_migrations.SchemaLock.write_lock_file",
                    side_effect=OSError("Permission denied"),
                ):
                    with patch("builtins.print"):
                        result = generate_lock("test.module")
                        assert result == 1

    def test_generate_lock_with_existing_migrations_file(self):
        """Test generate_lock reads existing migrations file"""
        mock_model = Mock()
        mock_model._meta.table_name = "test_table"

        migration_data = {
            "migrations": [
                {
                    "version": "20231201_001",
                    "sql": "CREATE TABLE test;",
                    "description": "Initial migration",
                }
            ]
        }

        with patch("kinglet.orm_deploy.import_models", return_value=[mock_model]):
            with patch("os.path.exists", return_value=True):
                with patch(
                    "builtins.open", mock_open(read_data=json.dumps(migration_data))
                ):
                    with patch(
                        "kinglet.orm_migrations.SchemaLock.generate_lock"
                    ) as mock_gen:
                        with patch("kinglet.orm_migrations.SchemaLock.write_lock_file"):
                            with patch("builtins.print"):
                                mock_gen.return_value = {
                                    "schema_hash": "test123",
                                    "models": {},
                                }

                                result = generate_lock("test.module")
                                assert result == 0
                                # Should have called generate_lock with models and migrations
                                assert mock_gen.called


class TestVerifySchemaErrorHandling:
    """Test schema verification error handling"""

    def test_verify_schema_exception(self):
        """Test verify_schema handles exceptions gracefully"""
        with patch(
            "kinglet.orm_deploy.import_models",
            side_effect=ImportError("Module not found"),
        ):
            with patch("builtins.print"):
                result = verify_schema("bad.module")
                assert result == 1

    def test_verify_schema_invalid_result(self):
        """Test verify_schema with invalid schema"""
        mock_model = Mock()

        # Mock schema verification returning invalid result with changes
        invalid_result = {
            "valid": False,
            "reason": "Schema hash mismatch",
            "action": "Generate new migration",
            "changes": {
                "added_models": ["NewModel"],
                "removed_models": ["OldModel"],
                "modified_models": ["ChangedModel"],
            },
        }

        with patch("kinglet.orm_deploy.import_models", return_value=[mock_model]):
            with patch(
                "kinglet.orm_migrations.SchemaLock.verify_schema",
                return_value=invalid_result,
            ):
                with patch("builtins.print") as mock_print:
                    result = verify_schema("test.module")
                    assert result == 1

                    # Should print detailed change information
                    print_calls = [call[0][0] for call in mock_print.call_args_list]
                    assert any("❌ Schema has changed!" in call for call in print_calls)
                    assert any("Added models: NewModel" in call for call in print_calls)
                    assert any(
                        "Removed models: OldModel" in call for call in print_calls
                    )


class TestGenerateMigrationsErrorHandling:
    """Test migration generation error handling"""

    def test_generate_migrations_no_lock_file(self):
        """Test generate_migrations when no lock file exists"""
        with patch(
            "kinglet.orm_migrations.SchemaLock.read_lock_file", return_value=None
        ):
            with patch("builtins.print"):
                result = generate_migrations("test.module")
                assert result == 1

    def test_generate_migrations_no_changes(self):
        """Test generate_migrations when schema hasn't changed"""
        mock_model = Mock()
        old_lock = {"schema_hash": "abc123", "models": {}}
        new_lock = {"schema_hash": "abc123", "models": {}}  # Same hash

        with patch("kinglet.orm_deploy.import_models", return_value=[mock_model]):
            with patch(
                "kinglet.orm_migrations.SchemaLock.read_lock_file",
                return_value=old_lock,
            ):
                with patch(
                    "kinglet.orm_migrations.SchemaLock.generate_lock",
                    return_value=new_lock,
                ):
                    with patch("builtins.print"):
                        result = generate_migrations("test.module")
                        assert result == 0  # No changes is success

    def test_generate_migrations_no_migrations_generated(self):
        """Test when schema changed but no migrations could be generated"""
        mock_model = Mock()
        old_lock = {"schema_hash": "abc123", "models": {}}
        new_lock = {"schema_hash": "def456", "models": {}}  # Different hash

        with patch("kinglet.orm_deploy.import_models", return_value=[mock_model]):
            with patch(
                "kinglet.orm_migrations.SchemaLock.read_lock_file",
                return_value=old_lock,
            ):
                with patch(
                    "kinglet.orm_migrations.SchemaLock.generate_lock",
                    return_value=new_lock,
                ):
                    with patch(
                        "kinglet.orm_migrations.MigrationGenerator.detect_changes",
                        return_value=[],
                    ):
                        with patch("builtins.print"):
                            result = generate_migrations("test.module")
                            assert result == 1

    def test_generate_migrations_exception(self):
        """Test generate_migrations handles exceptions"""
        with patch(
            "kinglet.orm_deploy.import_models",
            side_effect=Exception("Unexpected error"),
        ):
            with patch("builtins.print"):
                result = generate_migrations("test.module")
                assert result == 1


class TestDeploySchemaErrorHandling:
    """Test schema deployment error handling"""

    def test_deploy_schema_no_schema(self):
        """Test deploy_schema when schema generation returns empty"""
        with patch("kinglet.orm_deploy.generate_schema", return_value=""):
            result = deploy_schema("empty.module")
            assert result == 1

    def test_deploy_schema_invalid_database_name(self):
        """Test deploy_schema validates database name"""
        with patch(
            "kinglet.orm_deploy.generate_schema", return_value="CREATE TABLE test;"
        ):
            with patch("builtins.print"):
                # Invalid database name with special characters
                result = deploy_schema("test.module", database="DB; DROP TABLE users")
                assert result == 1

    def test_deploy_schema_subprocess_error(self):
        """Test deploy_schema handles subprocess errors"""
        with patch(
            "kinglet.orm_deploy.generate_schema", return_value="CREATE TABLE test;"
        ):
            # Mock the context manager for NamedTemporaryFile
            mock_file = Mock()
            mock_file.name = "/tmp/test_schema.sql"
            mock_file.write = Mock()  # Mock the write method

            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value = mock_file
                mock_temp.return_value.__exit__.return_value = None

                # Mock subprocess.run to return error
                mock_result = Mock()
                mock_result.returncode = 1
                mock_result.stderr = "Database connection failed"

                with patch("subprocess.run", return_value=mock_result):
                    with patch("builtins.print"):
                        with patch("os.unlink"):  # Prevent actual file deletion
                            result = deploy_schema("test.module")
                            assert result == 1


class TestFileSystemOperations:
    """Test file system operation error handling"""

    def test_temp_file_cleanup_on_exception(self):
        """Test temporary file is cleaned up even when deployment fails"""
        with patch(
            "kinglet.orm_deploy.generate_schema", return_value="CREATE TABLE test;"
        ):
            # Mock the context manager for NamedTemporaryFile
            mock_file = Mock()
            mock_file.name = "/tmp/test_schema.sql"
            mock_file.write = Mock()

            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value = mock_file
                mock_temp.return_value.__exit__.return_value = None

                with patch(
                    "subprocess.run", side_effect=Exception("Subprocess failed")
                ):
                    with patch("os.unlink") as mock_unlink:
                        with patch("builtins.print"):
                            # Exception should propagate but cleanup should still happen
                            with pytest.raises(Exception, match="Subprocess failed"):
                                deploy_schema("test.module")

                            # Should still attempt cleanup in finally block
                            mock_unlink.assert_called_once_with("/tmp/test_schema.sql")
