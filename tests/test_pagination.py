"""
Tests for kinglet.pagination module
Tests PageInfo, PaginatedResult, Paginator, and pagination utilities
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kinglet.pagination import (
    CursorPaginator,
    PageInfo,
    PaginatedResult,
    PaginationConfig,
    PaginationMixin,
    Paginator,
    create_pagination_urls,
    paginate_queryset,
)


class TestPageInfo:
    """Test PageInfo class"""

    def test_page_info_creation(self):
        """Test creating PageInfo instance"""
        page_info = PageInfo(
            page=2,
            per_page=10,
            total_count=100,
            total_pages=10,
            has_next=True,
            has_previous=True,
            next_page=3,
            previous_page=1,
        )

        assert page_info.page == 2
        assert page_info.per_page == 10
        assert page_info.total_count == 100
        assert page_info.total_pages == 10
        assert page_info.has_next is True
        assert page_info.has_previous is True
        assert page_info.next_page == 3
        assert page_info.previous_page == 1

    def test_from_query_first_page(self):
        """Test PageInfo.from_query for first page"""
        page_info = PageInfo.from_query(page=1, per_page=10, total_count=50)

        assert page_info.page == 1
        assert page_info.per_page == 10
        assert page_info.total_count == 50
        assert page_info.total_pages == 5
        assert page_info.has_next is True
        assert page_info.has_previous is False
        assert page_info.next_page == 2
        assert page_info.previous_page is None

    def test_from_query_middle_page(self):
        """Test PageInfo.from_query for middle page"""
        page_info = PageInfo.from_query(page=3, per_page=10, total_count=50)

        assert page_info.page == 3
        assert page_info.per_page == 10
        assert page_info.has_next is True
        assert page_info.has_previous is True
        assert page_info.next_page == 4
        assert page_info.previous_page == 2

    def test_from_query_last_page(self):
        """Test PageInfo.from_query for last page"""
        page_info = PageInfo.from_query(page=5, per_page=10, total_count=50)

        assert page_info.page == 5
        assert page_info.per_page == 10
        assert page_info.has_next is False
        assert page_info.has_previous is True
        assert page_info.next_page is None
        assert page_info.previous_page == 4

    def test_from_query_single_page(self):
        """Test PageInfo.from_query with only one page"""
        page_info = PageInfo.from_query(page=1, per_page=10, total_count=5)

        assert page_info.page == 1
        assert page_info.total_pages == 1
        assert page_info.has_next is False
        assert page_info.has_previous is False
        assert page_info.next_page is None
        assert page_info.previous_page is None

    def test_from_query_zero_per_page(self):
        """Test PageInfo.from_query with zero per_page"""
        page_info = PageInfo.from_query(page=1, per_page=0, total_count=50)

        assert page_info.total_pages == 0

    def test_from_query_partial_last_page(self):
        """Test PageInfo.from_query with partial last page"""
        page_info = PageInfo.from_query(page=1, per_page=10, total_count=25)

        assert page_info.total_pages == 3  # 25/10 = 2.5, ceil = 3


class TestPaginatedResult:
    """Test PaginatedResult class"""

    def test_paginated_result_creation(self):
        """Test creating PaginatedResult"""
        items = [{"id": 1, "name": "item1"}, {"id": 2, "name": "item2"}]
        page_info = PageInfo.from_query(1, 10, 50)

        result = PaginatedResult(items, page_info)

        assert result.items == items
        assert result.page_info is page_info

    def test_paginated_result_count_property(self):
        """Test count property returns current page item count"""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        page_info = PageInfo.from_query(1, 10, 50)

        result = PaginatedResult(items, page_info)

        assert result.count == 3

    def test_paginated_result_total_count_property(self):
        """Test total_count property returns page_info total"""
        items = [{"id": 1}]
        page_info = PageInfo.from_query(1, 10, 50)

        result = PaginatedResult(items, page_info)

        assert result.total_count == 50

    def test_paginated_result_page_properties(self):
        """Test page-related properties"""
        items = []
        page_info = PageInfo.from_query(2, 10, 50)

        result = PaginatedResult(items, page_info)

        assert result.page == 2
        assert result.per_page == 10
        assert result.has_next is True
        assert result.has_previous is True

    def test_to_dict_with_serialization(self):
        """Test to_dict with item serialization enabled"""

        class MockItem:
            def __init__(self, name):
                self.name = name

            def to_dict(self):
                return {"name": self.name, "serialized": True}

        items = [MockItem("item1"), MockItem("item2")]
        page_info = PageInfo.from_query(1, 10, 2)
        result = PaginatedResult(items, page_info)

        dict_result = result.to_dict()

        assert "pagination" in dict_result
        assert "items" in dict_result
        assert "count" in dict_result
        assert dict_result["count"] == 2
        assert len(dict_result["items"]) == 2
        assert dict_result["items"][0]["name"] == "item1"
        assert dict_result["items"][0]["serialized"] is True

    def test_to_dict_with_dict_items(self):
        """Test to_dict with objects having __dict__"""

        class SimpleItem:
            def __init__(self, name):
                self.name = name
                self.value = 42

        items = [SimpleItem("item1")]
        page_info = PageInfo.from_query(1, 10, 1)
        result = PaginatedResult(items, page_info)

        dict_result = result.to_dict()

        assert dict_result["items"][0]["name"] == "item1"
        assert dict_result["items"][0]["value"] == 42

    def test_to_dict_with_primitive_items(self):
        """Test to_dict with primitive items"""
        items = ["item1", "item2", "item3"]
        page_info = PageInfo.from_query(1, 10, 3)
        result = PaginatedResult(items, page_info)

        dict_result = result.to_dict()

        assert dict_result["items"] == ["item1", "item2", "item3"]

    def test_to_dict_without_serialization(self):
        """Test to_dict without item serialization"""
        items = [{"raw": "data"}]
        page_info = PageInfo.from_query(1, 10, 1)
        result = PaginatedResult(items, page_info)

        dict_result = result.to_dict(serialize_items=False)

        assert dict_result["items"] is items

    def test_map_method(self):
        """Test map method transforms items"""
        items = [1, 2, 3]
        page_info = PageInfo.from_query(1, 10, 3)
        result = PaginatedResult(items, page_info)

        mapped_result = result.map(lambda x: x * 2)

        assert mapped_result.items == [2, 4, 6]
        assert mapped_result.page_info is page_info  # Same page info


class TestPaginationConfig:
    """Test PaginationConfig class"""

    def test_config_defaults(self):
        """Test PaginationConfig default values"""
        config = PaginationConfig()

        assert config.default_per_page == 20
        assert config.max_per_page == 100
        assert config.min_per_page == 1
        assert config.page_param == "page"
        assert config.per_page_param == "per_page"
        assert config.count_query_timeout is None

    def test_config_custom_values(self):
        """Test PaginationConfig with custom values"""
        config = PaginationConfig(
            default_per_page=25,
            max_per_page=200,
            min_per_page=5,
            page_param="p",
            per_page_param="limit",
            count_query_timeout=5.0,
        )

        assert config.default_per_page == 25
        assert config.max_per_page == 200
        assert config.min_per_page == 5
        assert config.page_param == "p"
        assert config.per_page_param == "limit"
        assert config.count_query_timeout is not None
        import math

        assert math.isclose(config.count_query_timeout, 5.0)


class TestPaginator:
    """Test Paginator class"""

    def test_paginator_creation_default_config(self):
        """Test creating Paginator with default config"""
        paginator = Paginator()

        assert isinstance(paginator.config, PaginationConfig)
        assert paginator.config.default_per_page == 20

    def test_paginator_creation_custom_config(self):
        """Test creating Paginator with custom config"""
        config = PaginationConfig(default_per_page=50)
        paginator = Paginator(config)

        assert paginator.config is config
        assert paginator.config.default_per_page == 50

    def test_validate_params_normal_values(self):
        """Test validate_params with normal values"""
        paginator = Paginator()
        page, per_page = paginator.validate_params(5, 25)

        assert page == 5
        assert per_page == 25

    def test_validate_params_negative_page(self):
        """Test validate_params normalizes negative page"""
        paginator = Paginator()
        page, _ = paginator.validate_params(-1, 25)

        assert page == 1

    def test_validate_params_zero_page(self):
        """Test validate_params normalizes zero page"""
        paginator = Paginator()
        page, _ = paginator.validate_params(0, 25)

        assert page == 1

    def test_validate_params_per_page_too_small(self):
        """Test validate_params enforces min_per_page"""
        config = PaginationConfig(min_per_page=5)
        paginator = Paginator(config)
        _, per_page = paginator.validate_params(1, 2)

        assert per_page == 5

    def test_validate_params_per_page_too_large(self):
        """Test validate_params enforces max_per_page"""
        config = PaginationConfig(max_per_page=50)
        paginator = Paginator(config)
        _, per_page = paginator.validate_params(1, 100)

        assert per_page == 50

    def test_calculate_offset(self):
        """Test calculate_offset method"""
        paginator = Paginator()

        assert paginator.calculate_offset(1, 10) == 0
        assert paginator.calculate_offset(2, 10) == 10
        assert paginator.calculate_offset(3, 25) == 50

    @pytest.mark.asyncio
    async def test_paginate_query_basic(self):
        """Test paginate_query basic functionality"""
        # Mock query builders
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        mock_query = MagicMock()
        mock_query.limit.return_value.offset.return_value.all = AsyncMock(
            return_value=items
        )

        mock_count_query = MagicMock()
        mock_count_query.count = AsyncMock(return_value=50)

        paginator = Paginator()
        result = await paginator.paginate_query(
            mock_query, mock_count_query, page=2, per_page=10
        )

        assert isinstance(result, PaginatedResult)
        assert result.items == items
        assert result.total_count == 50
        assert result.page == 2
        assert result.per_page == 10

        # Verify query methods were called correctly
        mock_query.limit.assert_called_with(10)
        mock_query.limit.return_value.offset.assert_called_with(
            10
        )  # (page-1) * per_page

    @pytest.mark.asyncio
    async def test_paginate_query_default_per_page(self):
        """Test paginate_query uses default per_page"""
        mock_query = MagicMock()
        mock_query.limit.return_value.offset.return_value.all = AsyncMock(
            return_value=[]
        )

        mock_count_query = MagicMock()
        mock_count_query.count = AsyncMock(return_value=0)

        config = PaginationConfig(default_per_page=25)
        paginator = Paginator(config)
        result = await paginator.paginate_query(mock_query, mock_count_query)

        assert result.per_page == 25
        mock_query.limit.assert_called_with(25)

    @pytest.mark.asyncio
    async def test_paginate_query_count_fallback(self):
        """Test paginate_query falls back when count method doesn't exist"""
        mock_query = MagicMock()
        mock_query.limit.return_value.offset.return_value.all = AsyncMock(
            return_value=[{"id": 1}]
        )

        mock_count_query = MagicMock()
        # No count method, should fall back to all()
        del mock_count_query.count
        mock_count_query.all = AsyncMock(return_value=[{"id": 1}, {"id": 2}, {"id": 3}])

        paginator = Paginator()
        result = await paginator.paginate_query(mock_query, mock_count_query)

        assert result.total_count == 3  # From count query all()

    @pytest.mark.asyncio
    async def test_paginate_query_count_exception(self):
        """Test paginate_query handles count query exceptions"""
        mock_query = MagicMock()
        mock_query.limit.return_value.offset.return_value.all = AsyncMock(
            return_value=[{"id": 1}]
        )

        mock_count_query = MagicMock()
        mock_count_query.count = AsyncMock(side_effect=Exception("Count failed"))

        paginator = Paginator()
        result = await paginator.paginate_query(mock_query, mock_count_query)

        assert result.total_count == 0  # Falls back to 0 on exception

    @pytest.mark.asyncio
    async def test_paginate_query_with_timeout(self):
        """Test paginate_query with timeout configuration"""
        mock_query = MagicMock()
        mock_query.limit.return_value.offset.return_value.all = AsyncMock(
            return_value=[{"id": 1}]
        )

        mock_count_query = MagicMock()
        mock_count_query.count = AsyncMock(return_value=10)

        config = PaginationConfig(count_query_timeout=1.0)
        paginator = Paginator(config)

        with patch("asyncio.wait_for") as mock_wait_for:
            mock_wait_for.return_value = (10, [{"id": 1}])
            result = await paginator.paginate_query(mock_query, mock_count_query)

            assert result.total_count == 10
            mock_wait_for.assert_called_once()

    def test_paginate_list_basic(self):
        """Test paginate_list basic functionality"""
        items = list(range(1, 101))  # 1 to 100
        paginator = Paginator()

        result = paginator.paginate_list(items, page=2, per_page=10)

        assert isinstance(result, PaginatedResult)
        assert result.items == list(range(11, 21))  # Items 11-20
        assert result.total_count == 100
        assert result.page == 2
        assert result.per_page == 10

    def test_paginate_list_first_page(self):
        """Test paginate_list first page"""
        items = list(range(1, 26))  # 1 to 25
        paginator = Paginator()

        result = paginator.paginate_list(items, page=1, per_page=10)

        assert result.items == list(range(1, 11))  # Items 1-10
        assert result.has_previous is False
        assert result.has_next is True

    def test_paginate_list_last_page(self):
        """Test paginate_list last page with partial results"""
        items = list(range(1, 26))  # 1 to 25
        paginator = Paginator()

        result = paginator.paginate_list(items, page=3, per_page=10)

        assert result.items == list(range(21, 26))  # Items 21-25
        assert len(result.items) == 5
        assert result.has_next is False

    def test_paginate_list_beyond_last_page(self):
        """Test paginate_list beyond available pages"""
        items = list(range(1, 11))  # 1 to 10
        paginator = Paginator()

        result = paginator.paginate_list(items, page=5, per_page=10)

        assert result.items == []
        assert result.total_count == 10

    def test_paginate_list_default_per_page(self):
        """Test paginate_list uses default per_page"""
        items = list(range(1, 51))
        config = PaginationConfig(default_per_page=25)
        paginator = Paginator(config)

        result = paginator.paginate_list(items)

        assert result.per_page == 25
        assert len(result.items) == 25

    def test_parse_request_params(self):
        """Test parse_request_params method"""
        paginator = Paginator()
        request_params = {"page": "3", "per_page": "25"}

        page, per_page = paginator.parse_request_params(request_params)

        assert page == 3
        assert per_page == 25

    def test_parse_request_params_defaults(self):
        """Test parse_request_params with missing parameters"""
        config = PaginationConfig(default_per_page=50)
        paginator = Paginator(config)
        request_params = {}

        page, per_page = paginator.parse_request_params(request_params)

        assert page == 1
        assert per_page == 50

    def test_parse_request_params_custom_param_names(self):
        """Test parse_request_params with custom parameter names"""
        config = PaginationConfig(page_param="p", per_page_param="limit")
        paginator = Paginator(config)
        request_params = {"p": "2", "limit": "15"}

        page, per_page = paginator.parse_request_params(request_params)

        assert page == 2
        assert per_page == 15


class TestPaginationMixin:
    """Test PaginationMixin class"""

    def test_mixin_initialization(self):
        """Test PaginationMixin initialization"""

        class TestClass(PaginationMixin):
            def __init__(self):
                super().__init__()

        obj = TestClass()

        assert hasattr(obj, "_paginator")
        assert isinstance(obj._paginator, Paginator)

    def test_mixin_clone_for_count_default(self):
        """Test PaginationMixin default _clone_for_count"""

        class TestClass(PaginationMixin):
            def __init__(self):
                super().__init__()

        obj = TestClass()
        cloned = obj._clone_for_count()

        assert cloned is obj  # Default implementation returns self


class TestCursorPaginator:
    """Test CursorPaginator class"""

    def test_cursor_paginator_creation(self):
        """Test creating CursorPaginator"""
        paginator = CursorPaginator()

        assert paginator.cursor_field == "id"
        assert paginator.direction == "asc"

    def test_cursor_paginator_custom_field_and_direction(self):
        """Test CursorPaginator with custom field and direction"""
        paginator = CursorPaginator(cursor_field="created_at", direction="desc")

        assert paginator.cursor_field == "created_at"
        assert paginator.direction == "desc"

    def test_cursor_paginator_invalid_direction(self):
        """Test CursorPaginator raises error for invalid direction"""
        with pytest.raises(ValueError, match="Direction must be 'asc' or 'desc'"):
            CursorPaginator(direction="invalid")

    @pytest.mark.asyncio
    async def test_cursor_paginate_basic(self):
        """Test basic cursor pagination"""

        # Mock items with id field
        class MockItem:
            def __init__(self, id_val):
                self.id = id_val

        items = [MockItem(1), MockItem(2), MockItem(3)]

        mock_query = MagicMock()
        mock_query.order_by.return_value.limit.return_value.all = AsyncMock(
            return_value=items
        )

        paginator = CursorPaginator()
        result = await paginator.paginate(mock_query, limit=5)

        assert result["items"] == items
        assert result["page_info"]["has_next_page"] is False
        assert result["page_info"]["has_previous_page"] is False
        assert result["page_info"]["start_cursor"] == "1"
        assert result["page_info"]["end_cursor"] == "3"

        mock_query.order_by.assert_called_with("id")
        mock_query.order_by.return_value.limit.assert_called_with(6)  # limit + 1

    @pytest.mark.asyncio
    async def test_cursor_paginate_with_after_cursor(self):
        """Test cursor pagination with after_cursor"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.limit.return_value.all = AsyncMock(
            return_value=[]
        )

        paginator = CursorPaginator()
        await paginator.paginate(mock_query, after_cursor="10")

        mock_query.filter.assert_called_with(id__gt="10")

    @pytest.mark.asyncio
    async def test_cursor_paginate_with_before_cursor(self):
        """Test cursor pagination with before_cursor"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.limit.return_value.all = AsyncMock(
            return_value=[]
        )

        paginator = CursorPaginator()
        await paginator.paginate(mock_query, before_cursor="20")

        mock_query.filter.assert_called_with(id__lt="20")

    @pytest.mark.asyncio
    async def test_cursor_paginate_desc_direction(self):
        """Test cursor pagination with desc direction"""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.limit.return_value.all = AsyncMock(
            return_value=[]
        )

        paginator = CursorPaginator(direction="desc")
        await paginator.paginate(mock_query, after_cursor="10")

        mock_query.filter.assert_called_with(id__lt="10")
        mock_query.order_by.assert_called_with("-id")

    @pytest.mark.asyncio
    async def test_cursor_paginate_has_more_items(self):
        """Test cursor pagination with more items than limit"""

        class MockItem:
            def __init__(self, id_val):
                self.id = id_val

        # Return limit + 1 items
        items = [MockItem(i) for i in range(1, 7)]

        mock_query = MagicMock()
        mock_query.order_by.return_value.limit.return_value.all = AsyncMock(
            return_value=items
        )

        paginator = CursorPaginator()
        result = await paginator.paginate(mock_query, limit=5)

        assert len(result["items"]) == 5  # Trimmed to limit
        assert result["page_info"]["has_next_page"] is True

    @pytest.mark.asyncio
    async def test_cursor_paginate_empty_results(self):
        """Test cursor pagination with no results"""
        mock_query = MagicMock()
        mock_query.order_by.return_value.limit.return_value.all = AsyncMock(
            return_value=[]
        )

        paginator = CursorPaginator()
        result = await paginator.paginate(mock_query)

        assert result["items"] == []
        assert result["page_info"]["start_cursor"] is None
        assert result["page_info"]["end_cursor"] is None


class TestUtilityFunctions:
    """Test utility functions"""

    def test_create_pagination_urls_basic(self):
        """Test create_pagination_urls basic functionality"""
        page_info = PageInfo.from_query(3, 10, 100)
        urls = create_pagination_urls("https://api.example.com/items", page_info)

        assert urls["previous"] is not None and "page=2" in urls["previous"]
        assert urls["previous"] is not None and "per_page=10" in urls["previous"]
        assert urls["next"] is not None and "page=4" in urls["next"]
        assert urls["first"] is not None and "page=1" in urls["first"]
        assert urls["last"] is not None and "page=10" in urls["last"]

    def test_create_pagination_urls_with_query_params(self):
        """Test create_pagination_urls preserves existing query params"""
        page_info = PageInfo.from_query(2, 5, 25)
        query_params = {"category": "electronics", "sort": "name"}

        urls = create_pagination_urls(
            "https://api.example.com/items", page_info, query_params
        )

        assert urls["next"] is not None and "category=electronics" in urls["next"]
        assert urls["next"] is not None and "sort=name" in urls["next"]
        assert urls["next"] is not None and "page=3" in urls["next"]

    def test_create_pagination_urls_first_page(self):
        """Test create_pagination_urls for first page"""
        page_info = PageInfo.from_query(1, 10, 50)
        urls = create_pagination_urls("https://api.example.com/items", page_info)

        assert urls["previous"] is None
        assert urls["next"] is not None

    def test_create_pagination_urls_last_page(self):
        """Test create_pagination_urls for last page"""
        page_info = PageInfo.from_query(5, 10, 50)
        urls = create_pagination_urls("https://api.example.com/items", page_info)

        assert urls["next"] is None
        assert urls["previous"] is not None

    async def test_paginate_queryset_with_list(self):
        """Test paginate_queryset with list"""
        items = list(range(1, 26))  # 1 to 25
        result = await paginate_queryset(items, page=2, per_page=10)

        assert isinstance(result, PaginatedResult)
        assert result.items == list(range(11, 21))  # Items 11-20
        assert result.total_count == 25
