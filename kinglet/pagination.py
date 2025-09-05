"""
Kinglet Pagination System
Eliminates boilerplate for paginated queries and responses
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, TypeVar
from urllib.parse import urlencode

T = TypeVar("T")


@dataclass
class PageInfo:
    """Page information for pagination"""

    page: int
    per_page: int
    total_count: int
    total_pages: int
    has_next: bool
    has_previous: bool
    next_page: int | None = None
    previous_page: int | None = None

    @classmethod
    def from_query(cls, page: int, per_page: int, total_count: int) -> PageInfo:
        """Create PageInfo from query parameters"""
        total_pages = math.ceil(total_count / per_page) if per_page > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1

        return cls(
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
            next_page=page + 1 if has_next else None,
            previous_page=page - 1 if has_previous else None,
        )


@dataclass
class PaginatedResult[T]:
    """Container for paginated query results"""

    items: list[T]
    page_info: PageInfo

    @property
    def count(self) -> int:
        """Number of items in current page"""
        return len(self.items)

    @property
    def total_count(self) -> int:
        """Total number of items across all pages"""
        return self.page_info.total_count

    @property
    def page(self) -> int:
        """Current page number"""
        return self.page_info.page

    @property
    def per_page(self) -> int:
        """Items per page"""
        return self.page_info.per_page

    @property
    def has_next(self) -> bool:
        """Whether there is a next page"""
        return self.page_info.has_next

    @property
    def has_previous(self) -> bool:
        """Whether there is a previous page"""
        return self.page_info.has_previous

    def to_dict(self, serialize_items: bool = True) -> dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {"pagination": asdict(self.page_info), "count": self.count}

        if serialize_items:
            # Try to serialize items
            items_data = []
            for item in self.items:
                if hasattr(item, "to_dict"):
                    items_data.append(item.to_dict())
                elif hasattr(item, "__dict__"):
                    items_data.append(item.__dict__)
                else:
                    items_data.append(item)
            result["items"] = items_data
        else:
            result["items"] = self.items

        return result

    def map(self, func) -> PaginatedResult:
        """Apply function to all items, returning new PaginatedResult"""
        mapped_items = [func(item) for item in self.items]
        return PaginatedResult(mapped_items, self.page_info)


class PaginationConfig:
    """Configuration for pagination behavior"""

    def __init__(
        self,
        default_per_page: int = 20,
        max_per_page: int = 100,
        min_per_page: int = 1,
        page_param: str = "page",
        per_page_param: str = "per_page",
        count_query_timeout: float | None = None,
    ):
        self.default_per_page = default_per_page
        self.max_per_page = max_per_page
        self.min_per_page = min_per_page
        self.page_param = page_param
        self.per_page_param = per_page_param
        self.count_query_timeout = count_query_timeout


class Paginator:
    """Handles pagination logic and query building"""

    def __init__(self, config: PaginationConfig | None = None):
        self.config = config or PaginationConfig()

    def validate_params(self, page: int, per_page: int) -> tuple[int, int]:
        """Validate and normalize pagination parameters"""
        # Validate page number
        page = max(1, page)

        # Validate per_page
        per_page = max(
            self.config.min_per_page, min(per_page, self.config.max_per_page)
        )

        return page, per_page

    def calculate_offset(self, page: int, per_page: int) -> int:
        """Calculate offset for SQL queries"""
        return (page - 1) * per_page

    async def paginate_query(
        self,
        query_builder,
        count_query_builder,
        page: int = 1,
        per_page: int | None = None,
    ) -> PaginatedResult:
        """
        Paginate a query builder

        Args:
            query_builder: Query builder for items (should have limit/offset methods)
            count_query_builder: Query builder for counting total items
            page: Page number (1-based)
            per_page: Items per page

        Returns:
            PaginatedResult with items and pagination info
        """
        per_page = per_page or self.config.default_per_page
        page, per_page = self.validate_params(page, per_page)

        # Calculate offset
        offset = self.calculate_offset(page, per_page)

        # Execute count query and items query in parallel if possible
        import asyncio

        async def get_count():
            # Try to get count efficiently
            try:
                if hasattr(count_query_builder, "count"):
                    return await count_query_builder.count()
                else:
                    # Fallback to manual count
                    count_results = await count_query_builder.all()
                    return len(count_results)
            except Exception:
                # If count fails, return 0
                return 0

        async def get_items():
            return await query_builder.limit(per_page).offset(offset).all()

        # Execute both queries
        if self.config.count_query_timeout:
            try:
                total_count, items = await asyncio.wait_for(
                    asyncio.gather(get_count(), get_items()),
                    timeout=self.config.count_query_timeout,
                )
            except TimeoutError:
                # If queries timeout, just get items and estimate count
                items = await get_items()
                total_count = len(items) + offset  # Rough estimate
        else:
            total_count, items = await asyncio.gather(get_count(), get_items())

        # Create pagination info
        page_info = PageInfo.from_query(page, per_page, total_count)

        return PaginatedResult(items, page_info)

    def paginate_list(
        self, items: list[T], page: int = 1, per_page: int | None = None
    ) -> PaginatedResult[T]:
        """
        Paginate an in-memory list

        Args:
            items: List of items to paginate
            page: Page number (1-based)
            per_page: Items per page

        Returns:
            PaginatedResult with paginated items
        """
        per_page = per_page or self.config.default_per_page
        page, per_page = self.validate_params(page, per_page)

        total_count = len(items)
        offset = self.calculate_offset(page, per_page)

        # Slice the list for current page
        page_items = items[offset : offset + per_page]

        # Create pagination info
        page_info = PageInfo.from_query(page, per_page, total_count)

        return PaginatedResult(page_items, page_info)

    def parse_request_params(self, request_params: dict[str, Any]) -> tuple[int, int]:
        """
        Parse pagination parameters from request

        Args:
            request_params: Dictionary of request parameters

        Returns:
            Tuple of (page, per_page)
        """
        page = int(request_params.get(self.config.page_param, 1))
        per_page = int(
            request_params.get(self.config.per_page_param, self.config.default_per_page)
        )

        return self.validate_params(page, per_page)


class PaginationMixin:
    """
    Mixin for ORM query builders to add pagination support
    Add this to your QueryManager or QuerySet classes
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginator = Paginator()

    async def paginate(
        self,
        page: int = 1,
        per_page: int | None = None,
        config: PaginationConfig | None = None,
    ) -> PaginatedResult:
        """
        Paginate the current query

        Args:
            page: Page number (1-based)
            per_page: Items per page
            config: Optional pagination config

        Returns:
            PaginatedResult with items and pagination info
        """
        if config:
            paginator = Paginator(config)
        else:
            paginator = self._paginator

        # Create count query from current query
        count_query = self._clone_for_count()

        return await paginator.paginate_query(self, count_query, page, per_page)

    def _clone_for_count(self):
        """
        Create a clone of this query for counting
        Should be overridden by specific query builder implementations
        """
        # Default implementation - just return self
        # In practice, you'd want to remove ordering, select fields, etc.
        return self


class CursorPaginator:
    """
    Cursor-based pagination for large datasets
    More efficient than offset-based pagination for large pages
    """

    def __init__(self, cursor_field: str = "id", direction: str = "asc"):
        """
        Initialize cursor paginator

        Args:
            cursor_field: Field to use for cursor (should be unique and orderable)
            direction: Sort direction ('asc' or 'desc')
        """
        self.cursor_field = cursor_field
        self.direction = direction.lower()

        if self.direction not in ("asc", "desc"):
            raise ValueError("Direction must be 'asc' or 'desc'")

    async def paginate(
        self,
        query_builder,
        limit: int = 20,
        after_cursor: str | None = None,
        before_cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Paginate using cursor-based approach

        Args:
            query_builder: Query builder to paginate
            limit: Maximum number of items to return
            after_cursor: Cursor to get items after
            before_cursor: Cursor to get items before

        Returns:
            Dictionary with items and cursor information
        """
        # Build query with cursor filters
        if after_cursor:
            if self.direction == "asc":
                query_builder = query_builder.filter(
                    **{f"{self.cursor_field}__gt": after_cursor}
                )
            else:
                query_builder = query_builder.filter(
                    **{f"{self.cursor_field}__lt": after_cursor}
                )

        if before_cursor:
            if self.direction == "asc":
                query_builder = query_builder.filter(
                    **{f"{self.cursor_field}__lt": before_cursor}
                )
            else:
                query_builder = query_builder.filter(
                    **{f"{self.cursor_field}__gt": before_cursor}
                )

        # Apply ordering
        order_field = (
            f"-{self.cursor_field}" if self.direction == "desc" else self.cursor_field
        )
        query_builder = query_builder.order_by(order_field)

        # Get one extra item to check if there are more
        items = await query_builder.limit(limit + 1).all()

        has_next = len(items) > limit
        if has_next:
            items = items[:limit]  # Remove extra item

        # Generate cursors
        start_cursor = None
        end_cursor = None

        if items:
            start_cursor = str(getattr(items[0], self.cursor_field))
            end_cursor = str(getattr(items[-1], self.cursor_field))

        return {
            "items": items,
            "page_info": {
                "has_next_page": has_next,
                "has_previous_page": bool(after_cursor),
                "start_cursor": start_cursor,
                "end_cursor": end_cursor,
            },
        }


# Utility functions for pagination
def create_pagination_urls(
    base_url: str, page_info: PageInfo, query_params: dict[str, Any] | None = None
) -> dict[str, str | None]:
    """
    Create pagination URLs for API responses

    Args:
        base_url: Base URL for pagination links
        page_info: PageInfo object
        query_params: Additional query parameters to preserve

    Returns:
        Dictionary with next/previous URLs
    """
    query_params = query_params or {}

    def build_url(page_num):
        if page_num is None:
            return None
        params = query_params.copy()
        params["page"] = page_num
        params["per_page"] = page_info.per_page
        return f"{base_url}?{urlencode(params)}"

    return {
        "next": build_url(page_info.next_page),
        "previous": build_url(page_info.previous_page),
        "first": build_url(1),
        "last": build_url(page_info.total_pages),
    }


async def paginate_queryset(
    queryset,
    page: int = 1,
    per_page: int = 20,
    config: PaginationConfig | None = None,
) -> PaginatedResult:
    """
    Async function to paginate a queryset or list

    Args:
        queryset: Queryset or list to paginate
        page: Page number
        per_page: Items per page
        config: Optional pagination config

    Returns:
        PaginatedResult
    """
    paginator = Paginator(config)

    if hasattr(queryset, "limit") and hasattr(queryset, "offset"):
        # Assume it's a query builder - must await the async method
        count_query = queryset  # Simplified - in practice you'd clone for count
        return await paginator.paginate_query(queryset, count_query, page, per_page)
    else:
        # Assume it's a list
        return paginator.paginate_list(list(queryset), page, per_page)
