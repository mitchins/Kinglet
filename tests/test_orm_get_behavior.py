"""
Unit tests for Kinglet ORM get() behavior and DoesNotExist exceptions

Tests for the critical ORM behavior discovered during alpha testing:
- Manager.get() should raise DoesNotExist when no record found
- QuerySet.get() should raise DoesNotExist when no record found  
- All models should have a DoesNotExist exception class
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add the parent directory to the path so we can import kinglet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kinglet.orm import Model, StringField, IntegerField, DoesNotExistError


class ORMTestUser(Model):
    """Test model for ORM behavior testing"""
    username = StringField(max_length=50, null=False, unique=True)
    email = StringField(max_length=255, null=False, unique=True)
    age = IntegerField(null=True)
    
    class Meta:
        table_name = "test_users"


class TestORMGetBehavior:
    """Test ORM get() behavior and exception handling"""
    
    def setup_method(self):
        """Set up test environment"""
        self.mock_db = MagicMock()
        
    def test_model_has_doesnot_exist_class(self):
        """Test that models automatically get DoesNotExist exception class"""
        # This tests the fix in ModelMeta.__new__
        assert hasattr(ORMTestUser, 'DoesNotExist')
        assert issubclass(ORMTestUser.DoesNotExist, DoesNotExistError)
        
    def test_doesnot_exist_inheritance(self):
        """Test that DoesNotExist properly inherits from framework exception"""
        # Each model should have its own DoesNotExist class
        assert ORMTestUser.DoesNotExist != DoesNotExistError
        assert issubclass(ORMTestUser.DoesNotExist, DoesNotExistError)
        
    @pytest.mark.asyncio
    async def test_manager_get_raises_doesnot_exist(self):
        """Test that Manager.get() raises DoesNotExist when no record found"""
        
        # Create a mock queryset that behaves like a real QuerySet
        mock_filtered_queryset = AsyncMock()
        mock_filtered_queryset.get.side_effect = ORMTestUser.DoesNotExist("No ORMTestUser found")
        
        mock_base_queryset = MagicMock()
        mock_base_queryset.filter.return_value = mock_filtered_queryset
        
        # Mock the manager's get_queryset method
        ORMTestUser.objects.get_queryset = MagicMock(return_value=mock_base_queryset)
        
        # Test that get() properly raises the exception
        with pytest.raises(ORMTestUser.DoesNotExist):
            await ORMTestUser.objects.get(self.mock_db, username="nonexistent")
            
        # Verify the call chain
        ORMTestUser.objects.get_queryset.assert_called_once_with(self.mock_db)
        mock_base_queryset.filter.assert_called_once_with(username="nonexistent")
        mock_filtered_queryset.get.assert_called_once()
        
    @pytest.mark.asyncio 
    async def test_manager_get_returns_instance_when_found(self):
        """Test that Manager.get() returns model instance when record found"""
        
        # Create a mock user instance
        mock_user = ORMTestUser(username="testuser", email="test@example.com")
        mock_user.id = 1
        
        # Create a mock queryset that behaves like a real QuerySet
        mock_filtered_queryset = AsyncMock()
        mock_filtered_queryset.get.return_value = mock_user
        
        mock_base_queryset = MagicMock()
        mock_base_queryset.filter.return_value = mock_filtered_queryset
        
        # Mock the manager's get_queryset method
        ORMTestUser.objects.get_queryset = MagicMock(return_value=mock_base_queryset)
        
        # Test that get() returns the instance
        result = await ORMTestUser.objects.get(self.mock_db, username="testuser")
        
        assert result == mock_user
        assert result.username == "testuser"
        assert result.id == 1
        
    @pytest.mark.asyncio
    async def test_queryset_get_no_results(self):
        """Test QuerySet.get() behavior with no results - using the actual QuerySet get() method"""
        
        # Create a mock QuerySet with mocked all() method
        from kinglet.orm import QuerySet
        from unittest.mock import patch
        
        # Use patch to mock the all() method directly on the QuerySet class
        with patch.object(QuerySet, 'all', new_callable=AsyncMock) as mock_all:
            mock_all.return_value = []
            
            mock_queryset = QuerySet(ORMTestUser, self.mock_db)
            
            # Test that get() raises DoesNotExist for empty results
            with pytest.raises(DoesNotExistError):
                await mock_queryset.get()
            
    @pytest.mark.asyncio
    async def test_queryset_get_multiple_results(self):
        """Test QuerySet.get() behavior with multiple results"""
        
        # Create mock user instances
        user1 = ORMTestUser(username="user1", email="user1@example.com")
        user2 = ORMTestUser(username="user2", email="user2@example.com") 
        
        # Create a mock QuerySet with mocked all() method
        from kinglet.orm import QuerySet
        from unittest.mock import patch
        
        # Use patch to mock the all() method directly on the QuerySet class
        with patch.object(QuerySet, 'all', new_callable=AsyncMock) as mock_all:
            mock_all.return_value = [user1, user2]
            
            mock_queryset = QuerySet(ORMTestUser, self.mock_db)
            
            # Test that get() raises MultipleObjectsReturnedError for multiple results
            from kinglet.orm_errors import MultipleObjectsReturnedError
            with pytest.raises(MultipleObjectsReturnedError):
                await mock_queryset.get()
            
    @pytest.mark.asyncio
    async def test_queryset_get_single_result(self):
        """Test QuerySet.get() behavior with single result"""
        
        # Create a mock user instance
        user = ORMTestUser(username="testuser", email="test@example.com")
        user.id = 1
        
        # Create a mock QuerySet with mocked all() method
        from kinglet.orm import QuerySet
        from unittest.mock import patch
        
        # Use patch to mock the all() method directly on the QuerySet class
        with patch.object(QuerySet, 'all', new_callable=AsyncMock) as mock_all:
            mock_all.return_value = [user]
            
            mock_queryset = QuerySet(ORMTestUser, self.mock_db)
            
            # Test that get() returns the single instance
            result = await mock_queryset.get()
            
            assert result == user
            assert result.username == "testuser"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])