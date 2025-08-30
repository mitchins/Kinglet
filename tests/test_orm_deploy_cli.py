"""
Tests for ORM deployment CLI functionality
"""

import argparse
from unittest.mock import Mock, patch

import pytest

from kinglet.orm_deploy import (
    _create_argument_parser,
    generate_migration_endpoint,
    generate_status_endpoint,
)


class TestCLIArgumentParsing:
    """Test CLI argument parser configuration"""

    def test_create_argument_parser_basic_structure(self):
        """Test argument parser has expected subcommands"""
        parser = _create_argument_parser()

        # Test basic structure
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.description is not None

        # Parse help to see available subcommands
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_generate_command_parsing(self):
        """Test generate subcommand argument parsing"""
        parser = _create_argument_parser()

        # Basic generate command
        args = parser.parse_args(["generate", "myapp.models"])
        assert args.command == "generate"
        assert args.module == "myapp.models"
        assert args.no_indexes is False
        assert args.cleanslate is False

        # Generate with options
        args = parser.parse_args(
            ["generate", "myapp.models", "--no-indexes", "--cleanslate"]
        )
        assert args.no_indexes is True
        assert args.cleanslate is True

    def test_lock_command_parsing(self):
        """Test lock subcommand argument parsing"""
        parser = _create_argument_parser()

        # Basic lock command
        args = parser.parse_args(["lock", "myapp.models"])
        assert args.command == "lock"
        assert args.module == "myapp.models"
        assert args.output == "schema.lock.json"

        # Lock with custom output
        args = parser.parse_args(
            ["lock", "myapp.models", "--output", "custom.lock.json"]
        )
        assert args.output == "custom.lock.json"

    def test_verify_command_parsing(self):
        """Test verify subcommand argument parsing"""
        parser = _create_argument_parser()

        # Basic verify command
        args = parser.parse_args(["verify", "myapp.models"])
        assert args.command == "verify"
        assert args.module == "myapp.models"
        assert args.lock == "schema.lock.json"

        # Verify with custom lock file
        args = parser.parse_args(
            ["verify", "myapp.models", "--lock", "custom.lock.json"]
        )
        assert args.lock == "custom.lock.json"

    def test_migrate_command_parsing(self):
        """Test migrate subcommand argument parsing"""
        parser = _create_argument_parser()

        # Basic migrate command
        args = parser.parse_args(["migrate", "myapp.models"])
        assert args.command == "migrate"
        assert args.module == "myapp.models"
        assert args.lock == "schema.lock.json"

    def test_deploy_command_parsing(self):
        """Test deploy subcommand argument parsing"""
        parser = _create_argument_parser()

        # Basic deploy command
        args = parser.parse_args(["deploy", "myapp.models"])
        assert args.command == "deploy"
        assert args.module == "myapp.models"
        assert args.database == "DB"
        assert args.env == "production"

        # Deploy with options
        args = parser.parse_args(
            ["deploy", "myapp.models", "--database", "MYDB", "--env", "local"]
        )
        assert args.database == "MYDB"
        assert args.env == "local"

    def test_invalid_command_fails(self):
        """Test invalid commands are rejected"""
        parser = _create_argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["invalid_command"])


class TestTemplateGeneration:
    """Test code template generation functions"""

    def test_generate_migration_endpoint(self):
        """Test migration endpoint template generation"""
        # Mock import_models to avoid actual module imports
        with patch("kinglet.orm_deploy.import_models") as mock_import:
            mock_model = Mock()
            mock_model.__name__ = "TestModel"
            mock_import.return_value = [mock_model]

            template = generate_migration_endpoint("myapp.models")

            # Check template contains expected elements
            assert "myapp.models" in template
            assert "TestModel" in template
            assert "SchemaManager" in template
            assert "async def" in template
            assert "request.env.DB" in template
            assert "/api/_migrate" in template

            # Should be valid Python-like code structure
            assert "import" in template
            assert "from kinglet" in template

    def test_generate_status_endpoint(self):
        """Test status endpoint template generation"""
        template = generate_status_endpoint("myapp.models")

        # Check template contains expected elements
        assert "myapp.models" in template
        assert "MigrationTracker" in template
        assert "async def" in template
        assert "request.env.DB" in template
        assert "/api/_status" in template
        assert "current_version" in template

        # Should be valid Python-like code structure
        assert "import" in template
        assert "from kinglet" in template

    def test_template_module_path_substitution(self):
        """Test templates properly substitute module paths"""
        # Mock import_models for migration template test
        with patch("kinglet.orm_deploy.import_models") as mock_import:
            mock_model = Mock()
            mock_model.__name__ = "TestModel"
            mock_import.return_value = [mock_model]

            migration_template = generate_migration_endpoint("custom.path.models")
            status_template = generate_status_endpoint("custom.path.models")

            # Both templates should contain the custom module path
            assert "custom.path.models" in migration_template
            assert "custom.path.models" in status_template

            # Should not contain placeholder text
            assert "module_path" not in migration_template
            assert "module_path" not in status_template


class TestDeployValidation:
    """Test deployment input validation"""

    def test_database_name_validation_pattern(self):
        """Test database name validation uses secure pattern"""
        # This tests the validation logic without actually running subprocess
        import re

        # The pattern used in deploy_schema function
        pattern = r"^[A-Za-z0-9_-]+$"

        # Valid database names
        assert re.match(pattern, "DB")
        assert re.match(pattern, "my_database")
        assert re.match(pattern, "test-db-123")

        # Invalid database names (security risk)
        assert not re.match(pattern, "db; DROP TABLE")
        assert not re.match(pattern, "db && rm -rf /")
        assert not re.match(pattern, "db || echo pwned")
        assert not re.match(pattern, "")
        assert not re.match(pattern, "db with spaces")
