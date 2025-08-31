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


class TestVerifySchemaSuccess:
    """Test successful verify_schema operation"""

    def test_verify_schema_valid_case(self):
        """Test verify_schema when schema is valid - covers missing valid path"""
        from unittest.mock import patch

        from kinglet.orm_deploy import verify_schema

        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        # Mock successful verification result
        valid_result = {"valid": True, "schema_hash": "abc123", "models_count": 1}

        with patch("kinglet.orm_deploy.import_models", return_value=[mock_model]):
            with patch(
                "kinglet.orm_migrations.SchemaLock.verify_schema",
                return_value=valid_result,
            ):
                with patch("builtins.print") as mock_print:
                    result = verify_schema("test.module")

                    # Should return 0 for success
                    assert result == 0

                    # Should print success message
                    mock_print.assert_called()
                    print_args = [call.args[0] for call in mock_print.call_args_list]
                    success_message = "✅ Schema matches lock file"
                    assert any(success_message in arg for arg in print_args)

    def test_verify_schema_invalid_with_migrations_loop(self):
        """Test verify_schema invalid case that triggers 'for migration in migrations' loop"""
        from unittest.mock import patch

        from kinglet.orm_deploy import verify_schema

        mock_model = Mock()
        mock_model.__name__ = "TestModel"

        # Mock invalid result that would trigger migration loop
        invalid_result = {
            "valid": False,
            "reason": "Schema changed",
            "action": "Run migrations",
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

                    # Should return 1 for invalid schema
                    assert result == 1

                    # Should print all change details (covers the missing lines)
                    print_args = [call.args[0] for call in mock_print.call_args_list]
                    assert any("Added models: NewModel" in arg for arg in print_args)
                    assert any("Removed models: OldModel" in arg for arg in print_args)
                    assert any(
                        "Modified models: ChangedModel" in arg for arg in print_args
                    )


class TestExecuteCommandCoverage:
    """Test _execute_command function coverage"""

    def test_execute_command_all_branches(self):
        """Test _execute_command covers all command branches"""
        from unittest.mock import Mock, patch

        from kinglet.orm_deploy import _execute_command

        # Test each command branch
        test_cases = [
            ("generate", {"module": "test", "no_indexes": False, "cleanslate": False}),
            ("lock", {"module": "test", "output": "test.lock"}),
            ("verify", {"module": "test", "lock": "test.lock"}),
            ("migrate", {"module": "test", "lock": "test.lock"}),
            ("deploy", {"module": "test", "database": "DB", "env": "production"}),
            ("status", {"module": "test"}),
            ("endpoint", {"module": "test"}),
        ]

        for command, args_dict in test_cases:
            args = Mock()
            args.command = command
            for key, value in args_dict.items():
                setattr(args, key, value)

            # Mock all the functions that would be called
            with patch(
                "kinglet.orm_deploy.generate_schema", return_value="SQL"
            ) as mock_gen, patch(
                "kinglet.orm_deploy.generate_lock", return_value=0
            ) as mock_lock, patch(
                "kinglet.orm_deploy.verify_schema", return_value=0
            ) as mock_verify, patch(
                "kinglet.orm_deploy.generate_migrations", return_value=0
            ) as mock_migrate, patch(
                "kinglet.orm_deploy.deploy_schema", return_value=0
            ) as mock_deploy, patch(
                "kinglet.orm_deploy.generate_status_endpoint", return_value="CODE"
            ) as mock_status, patch(
                "kinglet.orm_deploy.generate_migration_endpoint", return_value="CODE"
            ) as mock_endpoint, patch("builtins.print"):
                result = _execute_command(args)
                assert result == 0

                # Verify the correct function was called
                if command == "generate":
                    mock_gen.assert_called_once()
                elif command == "lock":
                    mock_lock.assert_called_once()
                elif command == "verify":
                    mock_verify.assert_called_once()
                elif command == "migrate":
                    mock_migrate.assert_called_once()
                elif command == "deploy":
                    mock_deploy.assert_called_once()
                elif command == "status":
                    mock_status.assert_called_once()
                elif command == "endpoint":
                    mock_endpoint.assert_called_once()

    def test_execute_command_import_error(self):
        """Test _execute_command handles ImportError"""
        from unittest.mock import Mock, patch

        from kinglet.orm_deploy import _execute_command

        args = Mock()
        args.command = "generate"
        args.module = "test"
        args.no_indexes = False
        args.cleanslate = False

        with patch(
            "kinglet.orm_deploy.generate_schema",
            side_effect=ImportError("Module not found"),
        ):
            with patch("builtins.print") as mock_print:
                result = _execute_command(args)
                assert result == 1
                mock_print.assert_called()

    def test_execute_command_general_exception(self):
        """Test _execute_command handles general exceptions"""
        from unittest.mock import Mock, patch

        from kinglet.orm_deploy import _execute_command

        args = Mock()
        args.command = "generate"
        args.module = "test"
        args.no_indexes = False
        args.cleanslate = False

        with patch(
            "kinglet.orm_deploy.generate_schema", side_effect=Exception("General error")
        ):
            with patch("builtins.print") as mock_print:
                result = _execute_command(args)
                assert result == 1
                mock_print.assert_called()


class TestMainFunction:
    """Test main() function coverage"""

    def test_main_no_command(self):
        """Test main() when no command is provided"""
        from unittest.mock import patch

        from kinglet.orm_deploy import main

        with patch("sys.argv", ["orm_deploy.py"]):  # No command args
            with patch("kinglet.orm_deploy._create_argument_parser") as mock_parser:
                mock_parser_instance = Mock()
                mock_parser_instance.parse_args.return_value = Mock(command=None)
                mock_parser_instance.print_help = Mock()
                mock_parser.return_value = mock_parser_instance

                result = main()

                # Should return 1 and call print_help
                assert result == 1
                mock_parser_instance.print_help.assert_called_once()

    def test_main_with_command(self):
        """Test main() with valid command"""
        from unittest.mock import Mock, patch

        from kinglet.orm_deploy import main

        with patch("kinglet.orm_deploy._create_argument_parser") as mock_parser:
            mock_args = Mock()
            mock_args.command = "generate"
            mock_parser_instance = Mock()
            mock_parser_instance.parse_args.return_value = mock_args
            mock_parser.return_value = mock_parser_instance

            with patch(
                "kinglet.orm_deploy._execute_command", return_value=0
            ) as mock_execute:
                result = main()

                # Should return result from _execute_command
                assert result == 0
                mock_execute.assert_called_once_with(mock_args)
