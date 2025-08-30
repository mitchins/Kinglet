"""
Pytest configuration and fixtures for Kinglet tests

This file provides centralized test fixtures to reduce boilerplate
across the test suite, particularly for D1 database mocking.
"""

import pytest
from unittest.mock import patch

from .mock_d1 import MockD1Database, d1_unwrap, d1_unwrap_results


@pytest.fixture(autouse=True)
def d1_patches():
    """
    Auto-patch D1 unwrap functions for all tests
    
    This fixture automatically applies patches to d1_unwrap and d1_unwrap_results
    across all modules that use them, eliminating the need for manual patching
    in individual test methods.
    
    Patches applied:
    - kinglet.orm.d1_unwrap -> mock_d1.d1_unwrap
    - kinglet.orm.d1_unwrap_results -> mock_d1.d1_unwrap_results  
    - kinglet.orm_migrations.d1_unwrap -> mock_d1.d1_unwrap
    - kinglet.orm_migrations.d1_unwrap_results -> mock_d1.d1_unwrap_results
    """
    patches = [
        patch('kinglet.orm.d1_unwrap', d1_unwrap),
        patch('kinglet.orm.d1_unwrap_results', d1_unwrap_results),
        patch('kinglet.orm_migrations.d1_unwrap', d1_unwrap),
        patch('kinglet.orm_migrations.d1_unwrap_results', d1_unwrap_results),
    ]
    
    # Start all patches
    for p in patches:
        p.start()
    
    yield
    
    # Stop all patches
    for p in patches:
        p.stop()


@pytest.fixture
def mock_db():
    """
    Provide a fresh MockD1Database instance for tests
    
    Returns:
        MockD1Database: A clean in-memory SQLite database instance
                       that mimics D1's API for testing
    """
    return MockD1Database()