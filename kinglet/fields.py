"""
Kinglet Enhanced Field Types
Includes MediaField with automatic URL resolution and other specialized fields
"""

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .orm import StringField

# Constants for API endpoints
API_MEDIA_ENDPOINT = "/api/media"
TEST_MEDIA_ENDPOINT = "/test-media"


@dataclass
class MediaConfig:
    """Configuration for media handling"""

    # Base URL for media files (can be environment-specific)
    base_url: str | None = None

    # Storage path prefix
    path_prefix: str = "media"

    # Environment detection function
    environment_detector: Callable[[], str] | None = None

    # Environment-specific URL patterns
    environment_urls: dict[str, str] | None = None

    # Default placeholder URL when media is missing
    placeholder_url: str = "/placeholder.jpg"

    # Thumbnail settings
    thumbnail_suffix: str = "_thumb"
    thumbnail_sizes: list[int] | None = None

    # Allowed file types
    allowed_types: list[str] | None = None

    # Maximum file size in bytes
    max_file_size: int | None = None

    def __post_init__(self):
        if self.thumbnail_sizes is None:
            self.thumbnail_sizes = [150, 300, 600]

        if self.environment_urls is None:
            self.environment_urls = {
                "development": API_MEDIA_ENDPOINT,
                "testing": TEST_MEDIA_ENDPOINT,
                "production": None,  # Will use base_url
            }


class MediaUrlResolver:
    """Handles URL resolution for media files with environment awareness"""

    def __init__(self, config: MediaConfig):
        self.config = config

    def resolve_url(
        self, media_uid: str, thumbnail: bool = False, size: int | None = None
    ) -> str:
        """
        Resolve media UID to full URL

        Args:
            media_uid: Media identifier (usually UUID)
            thumbnail: Whether to get thumbnail version
            size: Specific thumbnail size (if supported)

        Returns:
            Full URL to media file
        """
        if not media_uid:
            return self.config.placeholder_url

        # Handle thumbnail suffix
        if thumbnail:
            if size and size in self.config.thumbnail_sizes:
                media_uid = f"{media_uid}_thumb_{size}"
            else:
                media_uid = f"{media_uid}{self.config.thumbnail_suffix}"

        # Get environment-specific base URL
        base_url = self._get_environment_base_url()

        if not base_url:
            return self.config.placeholder_url

        # Construct full URL
        if self.config.path_prefix:
            return f"{base_url}/{self.config.path_prefix}/{media_uid}"
        else:
            return f"{base_url}/{media_uid}"

    def resolve_thumbnail_url(self, media_uid: str, size: int | None = None) -> str:
        """Convenience method for thumbnail URLs"""
        return self.resolve_url(media_uid, thumbnail=True, size=size)

    def _get_environment_base_url(self) -> str | None:
        """Get base URL for current environment"""
        # If base_url is explicitly set, use it
        if self.config.base_url:
            return self.config.base_url

        # Detect environment
        environment = self._detect_environment()

        # Get environment-specific URL
        if environment in self.config.environment_urls:
            return self.config.environment_urls[environment]

        # Fallback to production URL or None
        return self.config.environment_urls.get("production")

    def _detect_environment(self) -> str:
        """Detect current environment"""
        if self.config.environment_detector:
            return self.config.environment_detector()

        # Default environment detection
        env = os.getenv("ENVIRONMENT", os.getenv("ENV", "production")).lower()

        if env in ["dev", "develop", "development", "local"]:
            return "development"
        elif env in ["test", "testing"]:
            return "testing"
        else:
            return "production"


class MediaFieldValue:
    """Wrapper for media field values with URL resolution"""

    def __init__(
        self,
        uid: str | None,
        resolver: MediaUrlResolver,
        metadata: dict[str, Any] | None = None,
    ):
        self.uid = uid
        self.resolver = resolver
        self.metadata = metadata or {}

    @property
    def url(self) -> str:
        """Get full media URL"""
        return self.resolver.resolve_url(self.uid)

    @property
    def thumbnail_url(self) -> str:
        """Get thumbnail URL"""
        return self.resolver.resolve_thumbnail_url(self.uid)

    def thumbnail_url_sized(self, size: int) -> str:
        """Get thumbnail URL for specific size"""
        return self.resolver.resolve_thumbnail_url(self.uid, size)

    @property
    def filename(self) -> str | None:
        """Get original filename if stored in metadata"""
        return self.metadata.get("filename")

    @property
    def content_type(self) -> str | None:
        """Get content type if stored in metadata"""
        return self.metadata.get("content_type")

    @property
    def size_bytes(self) -> int | None:
        """Get file size if stored in metadata"""
        return self.metadata.get("size_bytes")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {"uid": self.uid, "url": self.url, "thumbnail_url": self.thumbnail_url}

        # Add metadata if available
        if self.filename:
            result["filename"] = self.filename
        if self.content_type:
            result["content_type"] = self.content_type
        if self.size_bytes:
            result["size_bytes"] = self.size_bytes

        # Add different thumbnail sizes
        for size in self.resolver.config.thumbnail_sizes:
            result[f"thumbnail_url_{size}"] = self.thumbnail_url_sized(size)

        return result

    def __str__(self) -> str:
        """String representation returns the main URL"""
        return self.url

    def __bool__(self) -> bool:
        """Boolean representation based on whether UID exists"""
        return bool(self.uid)


class MediaField(StringField):
    """
    Enhanced field for media files with automatic URL resolution
    Eliminates boilerplate for media URL handling
    """

    def __init__(self, config: MediaConfig | None = None, **kwargs):
        """
        Initialize MediaField

        Args:
            config: MediaConfig for URL resolution
            **kwargs: Standard StringField arguments
        """
        super().__init__(**kwargs)
        self.config = config or MediaConfig()
        self.resolver = MediaUrlResolver(self.config)

    def to_python(self, value):
        """Convert database value to MediaFieldValue"""
        # Get base string value
        uid = super().to_python(value)

        if not uid:
            return MediaFieldValue(None, self.resolver)

        # Note: In a production implementation, metadata could be fetched from database
        # Currently using basic MediaFieldValue without database metadata lookup
        return MediaFieldValue(uid, self.resolver)

    def to_database(self, value):
        """Convert Python value to database value"""
        if isinstance(value, MediaFieldValue):
            return value.uid
        elif isinstance(value, str):
            return value
        elif value is None:
            return None
        else:
            return str(value)

    def validate(self, value):
        """Validate media field value"""
        super().validate(value)

        if value is None:
            return

        # Extract UID for validation
        if isinstance(value, MediaFieldValue):
            uid = value.uid
        elif isinstance(value, str):
            uid = value
        else:
            uid = str(value)

        # Validate file type if configured
        if self.config.allowed_types and uid:
            # Try to determine file type from UID or filename
            # This is a simple implementation - in practice you might store this metadata
            file_ext = None
            if "." in uid:
                file_ext = uid.split(".")[-1].lower()

            if file_ext and file_ext not in self.config.allowed_types:
                raise ValueError(
                    f"File type '{file_ext}' not allowed. Allowed types: {self.config.allowed_types}"
                )


class ImageField(MediaField):
    """Specialized MediaField for images with image-specific features"""

    def __init__(self, **kwargs):
        """Initialize ImageField with image defaults"""
        if "config" not in kwargs:
            config = MediaConfig(
                allowed_types=["jpg", "jpeg", "png", "gif", "webp"],
                max_file_size=10 * 1024 * 1024,  # 10MB
                placeholder_url="/placeholder-image.jpg",
            )
            kwargs["config"] = config

        super().__init__(**kwargs)


class VideoField(MediaField):
    """Specialized MediaField for videos"""

    def __init__(self, **kwargs):
        """Initialize VideoField with video defaults"""
        if "config" not in kwargs:
            config = MediaConfig(
                allowed_types=["mp4", "webm", "ogg", "avi", "mov"],
                max_file_size=500 * 1024 * 1024,  # 500MB
                placeholder_url="/placeholder-video.jpg",
                thumbnail_suffix="_poster",  # Video thumbnails are often called posters
            )
            kwargs["config"] = config

        super().__init__(**kwargs)


class DocumentField(MediaField):
    """Specialized MediaField for documents"""

    def __init__(self, **kwargs):
        """Initialize DocumentField with document defaults"""
        if "config" not in kwargs:
            config = MediaConfig(
                allowed_types=["pdf", "doc", "docx", "txt", "rtf"],
                max_file_size=50 * 1024 * 1024,  # 50MB
                placeholder_url="/placeholder-document.jpg",
                thumbnail_sizes=[200],  # Documents usually need just one thumbnail size
            )
            kwargs["config"] = config

        super().__init__(**kwargs)


# Utility functions for media handling
def generate_media_uid() -> str:
    """Generate a unique media identifier"""
    return str(uuid.uuid4())


def create_media_field_value(
    uid: str, resolver: MediaUrlResolver, **metadata
) -> MediaFieldValue:
    """Create a MediaFieldValue with metadata"""
    return MediaFieldValue(uid, resolver, metadata)


def resolve_media_url(
    uid: str, config: MediaConfig | None = None, thumbnail: bool = False
) -> str:
    """Quick function to resolve a media URL"""
    config = config or MediaConfig()
    resolver = MediaUrlResolver(config)
    return resolver.resolve_url(uid, thumbnail)


# Environment-specific URL helpers
def create_development_media_config(
    api_prefix: str = API_MEDIA_ENDPOINT,
) -> MediaConfig:
    """Create MediaConfig for development environment"""
    return MediaConfig(
        environment_urls={
            "development": api_prefix,
            "testing": TEST_MEDIA_ENDPOINT,
            "production": None,
        }
    )


def create_production_media_config(cdn_url: str) -> MediaConfig:
    """Create MediaConfig for production with CDN"""
    return MediaConfig(
        base_url=cdn_url,
        environment_urls={
            "development": API_MEDIA_ENDPOINT,
            "testing": TEST_MEDIA_ENDPOINT,
            "production": cdn_url,
        },
    )
