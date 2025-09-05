"""
Tests for kinglet.fields module
Tests MediaField, ImageField, VideoField, DocumentField, and related functionality
"""

import os
import uuid
from unittest.mock import patch

import pytest

from kinglet.fields import (
    API_MEDIA_ENDPOINT,
    TEST_MEDIA_ENDPOINT,
    DocumentField,
    ImageField,
    MediaConfig,
    MediaField,
    MediaFieldValue,
    MediaUrlResolver,
    VideoField,
    create_development_media_config,
    create_media_field_value,
    create_production_media_config,
    generate_media_uid,
    resolve_media_url,
)


class TestMediaConfig:
    """Test MediaConfig class"""

    def test_config_defaults(self):
        """Test MediaConfig with default values"""
        config = MediaConfig()

        assert config.base_url is None
        assert config.path_prefix == "media"
        assert config.environment_detector is None
        assert config.placeholder_url == "/placeholder.jpg"
        assert config.thumbnail_suffix == "_thumb"
        assert config.allowed_types is None
        assert config.max_file_size is None

    def test_config_post_init_thumbnail_sizes(self):
        """Test MediaConfig __post_init__ sets default thumbnail sizes"""
        config = MediaConfig()

        assert config.thumbnail_sizes == [150, 300, 600]

    def test_config_post_init_environment_urls(self):
        """Test MediaConfig __post_init__ sets default environment URLs"""
        config = MediaConfig()

        expected_urls = {
            "development": API_MEDIA_ENDPOINT,
            "testing": TEST_MEDIA_ENDPOINT,
            "production": None,
        }
        assert config.environment_urls == expected_urls

    def test_config_custom_values(self):
        """Test MediaConfig with custom values"""

        def custom_detector():
            return "custom_env"

        config = MediaConfig(
            base_url="https://cdn.example.com",
            path_prefix="assets",
            environment_detector=custom_detector,
            placeholder_url="/no-image.png",
            thumbnail_suffix="_small",
            thumbnail_sizes=[100, 200],
            allowed_types=["jpg", "png"],
            max_file_size=1024 * 1024,
        )

        assert config.base_url == "https://cdn.example.com"
        assert config.path_prefix == "assets"
        assert config.environment_detector is custom_detector
        assert config.placeholder_url == "/no-image.png"
        assert config.thumbnail_suffix == "_small"
        assert config.thumbnail_sizes == [100, 200]
        assert config.allowed_types == ["jpg", "png"]
        assert config.max_file_size == 1024 * 1024

    def test_config_custom_environment_urls(self):
        """Test MediaConfig with custom environment URLs"""
        custom_urls = {
            "development": "/dev-media",
            "production": "https://prod-cdn.com/media",
        }
        config = MediaConfig(environment_urls=custom_urls)

        assert config.environment_urls == custom_urls

    def test_config_preserves_custom_thumbnail_sizes(self):
        """Test MediaConfig preserves custom thumbnail sizes"""
        config = MediaConfig(thumbnail_sizes=[250, 500, 1000])

        assert config.thumbnail_sizes == [250, 500, 1000]


class TestMediaUrlResolver:
    """Test MediaUrlResolver class"""

    def test_resolver_creation(self):
        """Test creating MediaUrlResolver"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        assert resolver.config is config

    def test_resolve_url_with_empty_uid(self):
        """Test resolve_url with empty UID returns placeholder"""
        config = MediaConfig(placeholder_url="/no-media.jpg")
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("")

        assert result == "/no-media.jpg"

    def test_resolve_url_with_none_uid(self):
        """Test resolve_url with None UID returns placeholder"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url(None)

        assert result == "/placeholder.jpg"

    @patch.object(
        MediaUrlResolver,
        "_get_environment_base_url",
        return_value="https://cdn.example.com",
    )
    def test_resolve_url_basic(self, mock_get_base):
        """Test resolve_url basic functionality"""
        config = MediaConfig(path_prefix="media")
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("test-123")

        assert result == "https://cdn.example.com/media/test-123"

    @patch.object(
        MediaUrlResolver,
        "_get_environment_base_url",
        return_value="https://cdn.example.com",
    )
    def test_resolve_url_no_path_prefix(self, mock_get_base):
        """Test resolve_url without path prefix"""
        config = MediaConfig(path_prefix="")
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("test-123")

        assert result == "https://cdn.example.com/test-123"

    @patch.object(MediaUrlResolver, "_get_environment_base_url", return_value=None)
    def test_resolve_url_no_base_url(self, mock_get_base):
        """Test resolve_url when no base URL is available"""
        config = MediaConfig(placeholder_url="/fallback.jpg")
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("test-123")

        assert result == "/fallback.jpg"

    @patch.object(
        MediaUrlResolver,
        "_get_environment_base_url",
        return_value="https://cdn.example.com",
    )
    def test_resolve_url_thumbnail(self, mock_get_base):
        """Test resolve_url with thumbnail"""
        config = MediaConfig(thumbnail_suffix="_thumb")
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("test-123", thumbnail=True)

        assert result == "https://cdn.example.com/media/test-123_thumb"

    @patch.object(
        MediaUrlResolver,
        "_get_environment_base_url",
        return_value="https://cdn.example.com",
    )
    def test_resolve_url_thumbnail_with_size(self, mock_get_base):
        """Test resolve_url with thumbnail and specific size"""
        config = MediaConfig(thumbnail_sizes=[150, 300, 600])
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("test-123", thumbnail=True, size=300)

        assert result == "https://cdn.example.com/media/test-123_thumb_300"

    @patch.object(
        MediaUrlResolver,
        "_get_environment_base_url",
        return_value="https://cdn.example.com",
    )
    def test_resolve_url_thumbnail_invalid_size(self, mock_get_base):
        """Test resolve_url with thumbnail and invalid size falls back to suffix"""
        config = MediaConfig(thumbnail_sizes=[150, 300, 600], thumbnail_suffix="_small")
        resolver = MediaUrlResolver(config)

        result = resolver.resolve_url("test-123", thumbnail=True, size=999)

        assert result == "https://cdn.example.com/media/test-123_small"

    def test_resolve_thumbnail_url(self):
        """Test resolve_thumbnail_url convenience method"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        with patch.object(
            resolver, "resolve_url", return_value="thumbnail_url"
        ) as mock_resolve:
            result = resolver.resolve_thumbnail_url("test-123")

            mock_resolve.assert_called_with("test-123", thumbnail=True, size=None)
            assert result == "thumbnail_url"

    def test_resolve_thumbnail_url_with_size(self):
        """Test resolve_thumbnail_url with size"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        with patch.object(
            resolver, "resolve_url", return_value="sized_thumbnail"
        ) as mock_resolve:
            result = resolver.resolve_thumbnail_url("test-123", 300)

            mock_resolve.assert_called_with("test-123", thumbnail=True, size=300)
            assert result == "sized_thumbnail"

    def test_get_environment_base_url_explicit_base_url(self):
        """Test _get_environment_base_url with explicit base_url"""
        config = MediaConfig(base_url="https://explicit.cdn.com")
        resolver = MediaUrlResolver(config)

        result = resolver._get_environment_base_url()

        assert result == "https://explicit.cdn.com"

    @patch.object(MediaUrlResolver, "_detect_environment", return_value="development")
    def test_get_environment_base_url_from_environment(self, mock_detect):
        """Test _get_environment_base_url gets URL from environment"""
        config = MediaConfig(environment_urls={"development": "/dev-api"})
        resolver = MediaUrlResolver(config)

        result = resolver._get_environment_base_url()

        assert result == "/dev-api"

    @patch.object(MediaUrlResolver, "_detect_environment", return_value="unknown")
    def test_get_environment_base_url_fallback_to_production(self, mock_detect):
        """Test _get_environment_base_url falls back to production"""
        config = MediaConfig(environment_urls={"production": "https://prod.cdn.com"})
        resolver = MediaUrlResolver(config)

        result = resolver._get_environment_base_url()

        assert result == "https://prod.cdn.com"

    @patch.object(MediaUrlResolver, "_detect_environment", return_value="unknown")
    def test_get_environment_base_url_no_fallback(self, mock_detect):
        """Test _get_environment_base_url with no production fallback"""
        config = MediaConfig(environment_urls={"development": "/dev"})
        resolver = MediaUrlResolver(config)

        result = resolver._get_environment_base_url()

        assert result is None

    def test_detect_environment_with_custom_detector(self):
        """Test _detect_environment with custom detector"""

        def custom_detector():
            return "custom_env"

        config = MediaConfig(environment_detector=custom_detector)
        resolver = MediaUrlResolver(config)

        result = resolver._detect_environment()

        assert result == "custom_env"

    @patch.dict(os.environ, {"ENVIRONMENT": "development"})
    def test_detect_environment_from_environment_var(self):
        """Test _detect_environment from ENVIRONMENT variable"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        result = resolver._detect_environment()

        assert result == "development"

    @patch.dict(os.environ, {"ENV": "test"})
    def test_detect_environment_from_env_var(self):
        """Test _detect_environment from ENV variable"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        result = resolver._detect_environment()

        assert result == "testing"

    @patch.dict(os.environ, {}, clear=True)
    def test_detect_environment_default(self):
        """Test _detect_environment defaults to production"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        result = resolver._detect_environment()

        assert result == "production"

    @patch.dict(os.environ, {"ENVIRONMENT": "dev"})
    def test_detect_environment_dev_aliases(self):
        """Test _detect_environment recognizes dev aliases"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        assert resolver._detect_environment() == "development"

    @patch.dict(os.environ, {"ENVIRONMENT": "local"})
    def test_detect_environment_local_alias(self):
        """Test _detect_environment recognizes local alias"""
        config = MediaConfig()
        resolver = MediaUrlResolver(config)

        assert resolver._detect_environment() == "development"


class TestMediaFieldValue:
    """Test MediaFieldValue class"""

    def test_creation_with_uid(self):
        """Test creating MediaFieldValue with UID"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("test-uid", resolver)

        assert field_value.uid == "test-uid"
        assert field_value.resolver is resolver
        assert field_value.metadata == {}

    def test_creation_with_metadata(self):
        """Test creating MediaFieldValue with metadata"""
        resolver = MediaUrlResolver(MediaConfig())
        metadata = {"filename": "test.jpg", "size_bytes": 1024}
        field_value = MediaFieldValue("test-uid", resolver, metadata)

        assert field_value.metadata == metadata

    def test_url_property(self):
        """Test url property"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("test-uid", resolver)

        with patch.object(
            resolver, "resolve_url", return_value="full_url"
        ) as mock_resolve:
            url = field_value.url

            mock_resolve.assert_called_with("test-uid")
            assert url == "full_url"

    def test_thumbnail_url_property(self):
        """Test thumbnail_url property"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("test-uid", resolver)

        with patch.object(
            resolver, "resolve_thumbnail_url", return_value="thumb_url"
        ) as mock_resolve:
            url = field_value.thumbnail_url

            mock_resolve.assert_called_with("test-uid")
            assert url == "thumb_url"

    def test_thumbnail_url_sized(self):
        """Test thumbnail_url_sized method"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("test-uid", resolver)

        with patch.object(
            resolver, "resolve_thumbnail_url", return_value="sized_thumb"
        ) as mock_resolve:
            url = field_value.thumbnail_url_sized(300)

            mock_resolve.assert_called_with("test-uid", 300)
            assert url == "sized_thumb"

    def test_filename_property(self):
        """Test filename property"""
        resolver = MediaUrlResolver(MediaConfig())
        metadata = {"filename": "document.pdf"}
        field_value = MediaFieldValue("test-uid", resolver, metadata)

        assert field_value.filename == "document.pdf"

    def test_filename_property_missing(self):
        """Test filename property when not in metadata"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("test-uid", resolver)

        assert field_value.filename is None

    def test_content_type_property(self):
        """Test content_type property"""
        resolver = MediaUrlResolver(MediaConfig())
        metadata = {"content_type": "image/jpeg"}
        field_value = MediaFieldValue("test-uid", resolver, metadata)

        assert field_value.content_type == "image/jpeg"

    def test_size_bytes_property(self):
        """Test size_bytes property"""
        resolver = MediaUrlResolver(MediaConfig())
        metadata = {"size_bytes": 2048}
        field_value = MediaFieldValue("test-uid", resolver, metadata)

        assert field_value.size_bytes == 2048

    def test_bool_method_with_uid(self):
        """Test __bool__ method with UID"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("test-uid", resolver)

        assert bool(field_value) is True

    def test_bool_method_without_uid(self):
        """Test __bool__ method without UID"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue(None, resolver)

        assert bool(field_value) is False

    def test_bool_method_empty_uid(self):
        """Test __bool__ method with empty UID"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = MediaFieldValue("", resolver)

        assert bool(field_value) is False


class TestMediaField:
    """Test MediaField class"""

    def test_field_creation_default_config(self):
        """Test creating MediaField with default config"""
        field = MediaField()

        assert isinstance(field.config, MediaConfig)
        assert isinstance(field.resolver, MediaUrlResolver)

    def test_field_creation_custom_config(self):
        """Test creating MediaField with custom config"""
        config = MediaConfig(base_url="https://custom.cdn.com")
        field = MediaField(config=config)

        assert field.config is config

    def test_to_python_none_value(self):
        """Test to_python with None value"""
        field = MediaField()
        result = field.to_python(None)

        assert isinstance(result, MediaFieldValue)
        assert result.uid is None

    def test_to_python_empty_value(self):
        """Test to_python with empty value"""
        field = MediaField()
        result = field.to_python("")

        assert isinstance(result, MediaFieldValue)
        assert result.uid is None

    def test_to_python_with_uid(self):
        """Test to_python with valid UID"""
        field = MediaField()
        result = field.to_python("test-uid-123")

        assert isinstance(result, MediaFieldValue)
        assert result.uid == "test-uid-123"

    def test_to_database_with_media_field_value(self):
        """Test to_database with MediaFieldValue"""
        field = MediaField()
        resolver = field.resolver
        field_value = MediaFieldValue("test-uid", resolver)

        result = field.to_database(field_value)

        assert result == "test-uid"

    def test_to_database_with_string(self):
        """Test to_database with string value"""
        field = MediaField()
        result = field.to_database("string-uid")

        assert result == "string-uid"

    def test_to_database_with_none(self):
        """Test to_database with None value"""
        field = MediaField()
        result = field.to_database(None)

        assert result is None

    def test_to_database_with_other_type(self):
        """Test to_database with other type converts to string"""
        field = MediaField()
        result = field.to_database(123)

        assert result == "123"

    def test_validate_with_allowed_types(self):
        """Test validate with allowed types configuration"""
        config = MediaConfig(allowed_types=["jpg", "png", "gif"])
        field = MediaField(config=config)

        # Valid type should not raise
        field.validate("image.jpg")
        field.validate("photo.png")

    def test_validate_with_disallowed_type(self):
        """Test validate raises error for disallowed type"""
        config = MediaConfig(allowed_types=["jpg", "png"])
        field = MediaField(config=config)

        with pytest.raises(ValueError, match="File type 'gif' not allowed"):
            field.validate("image.gif")

    def test_validate_with_media_field_value(self):
        """Test validate with MediaFieldValue object"""
        config = MediaConfig(allowed_types=["jpg"])
        field = MediaField(config=config)
        field_value = MediaFieldValue("test.jpg", field.resolver)

        # Should not raise
        field.validate(field_value)

    def test_validate_with_none(self):
        """Test validate with None value"""
        config = MediaConfig(allowed_types=["jpg"])
        field = MediaField(config=config)

        # Should not raise for None
        field.validate(None)

    def test_validate_no_file_extension(self):
        """Test validate with UID that has no file extension"""
        config = MediaConfig(allowed_types=["jpg"])
        field = MediaField(config=config)

        # Should not raise for UID without extension
        field.validate("uuid-without-extension")

    def test_validate_no_allowed_types_config(self):
        """Test validate when no allowed_types configured"""
        field = MediaField()

        # Should not raise when no restrictions
        field.validate("any-file.xyz")


class TestImageField:
    """Test ImageField specialized media field"""

    def test_image_field_creation(self):
        """Test creating ImageField"""
        field = ImageField()

        assert isinstance(field, MediaField)
        assert field.config.allowed_types == ["jpg", "jpeg", "png", "gif", "webp"]
        assert field.config.max_file_size == 10 * 1024 * 1024  # 10MB
        assert field.config.placeholder_url == "/placeholder-image.jpg"

    def test_image_field_custom_config(self):
        """Test creating ImageField with custom config"""
        custom_config = MediaConfig(base_url="https://images.cdn.com")
        field = ImageField(config=custom_config)

        assert field.config is custom_config


class TestVideoField:
    """Test VideoField specialized media field"""

    def test_video_field_creation(self):
        """Test creating VideoField"""
        field = VideoField()

        assert isinstance(field, MediaField)
        assert field.config.allowed_types == ["mp4", "webm", "ogg", "avi", "mov"]
        assert field.config.max_file_size == 500 * 1024 * 1024  # 500MB
        assert field.config.placeholder_url == "/placeholder-video.jpg"
        assert field.config.thumbnail_suffix == "_poster"

    def test_video_field_custom_config(self):
        """Test creating VideoField with custom config"""
        custom_config = MediaConfig(base_url="https://videos.cdn.com")
        field = VideoField(config=custom_config)

        assert field.config is custom_config


class TestDocumentField:
    """Test DocumentField specialized media field"""

    def test_document_field_creation(self):
        """Test creating DocumentField"""
        field = DocumentField()

        assert isinstance(field, MediaField)
        assert field.config.allowed_types == ["pdf", "doc", "docx", "txt", "rtf"]
        assert field.config.max_file_size == 50 * 1024 * 1024  # 50MB
        assert field.config.placeholder_url == "/placeholder-document.jpg"
        assert field.config.thumbnail_sizes == [200]

    def test_document_field_custom_config(self):
        """Test creating DocumentField with custom config"""
        custom_config = MediaConfig(base_url="https://docs.cdn.com")
        field = DocumentField(config=custom_config)

        assert field.config is custom_config


class TestUtilityFunctions:
    """Test utility functions"""

    def test_generate_media_uid(self):
        """Test generate_media_uid creates valid UUID"""
        uid = generate_media_uid()

        assert isinstance(uid, str)
        assert len(uid) == 36  # Standard UUID length
        # Verify it's a valid UUID by parsing it
        uuid.UUID(uid)

    def test_generate_media_uid_unique(self):
        """Test generate_media_uid generates unique values"""
        uid1 = generate_media_uid()
        uid2 = generate_media_uid()

        assert uid1 != uid2

    def test_create_media_field_value(self):
        """Test create_media_field_value utility"""
        resolver = MediaUrlResolver(MediaConfig())
        field_value = create_media_field_value(
            "test-uid", resolver, filename="test.jpg", size=1024
        )

        assert isinstance(field_value, MediaFieldValue)
        assert field_value.uid == "test-uid"
        assert field_value.resolver is resolver
        assert field_value.metadata["filename"] == "test.jpg"
        assert field_value.metadata["size"] == 1024

    def test_resolve_media_url_default_config(self):
        """Test resolve_media_url utility with default config"""
        with patch("kinglet.fields.MediaUrlResolver") as MockResolver:
            mock_instance = MockResolver.return_value
            mock_instance.resolve_url.return_value = "resolved_url"

            result = resolve_media_url("test-uid")

            MockResolver.assert_called_once()
            mock_instance.resolve_url.assert_called_with("test-uid", False)
            assert result == "resolved_url"

    def test_resolve_media_url_custom_config(self):
        """Test resolve_media_url utility with custom config"""
        custom_config = MediaConfig(base_url="https://custom.com")

        with patch("kinglet.fields.MediaUrlResolver") as MockResolver:
            mock_instance = MockResolver.return_value
            mock_instance.resolve_url.return_value = "custom_url"

            result = resolve_media_url("test-uid", custom_config, thumbnail=True)

            MockResolver.assert_called_with(custom_config)
            mock_instance.resolve_url.assert_called_with("test-uid", True)
            assert result == "custom_url"

    def test_create_development_media_config(self):
        """Test create_development_media_config utility"""
        config = create_development_media_config()

        expected_urls = {
            "development": API_MEDIA_ENDPOINT,
            "testing": TEST_MEDIA_ENDPOINT,
            "production": None,
        }
        assert config.environment_urls == expected_urls

    def test_create_development_media_config_custom_prefix(self):
        """Test create_development_media_config with custom prefix"""
        config = create_development_media_config("/custom-api")

        expected_urls = {
            "development": "/custom-api",
            "testing": TEST_MEDIA_ENDPOINT,
            "production": None,
        }
        assert config.environment_urls == expected_urls

    def test_create_production_media_config(self):
        """Test create_production_media_config utility"""
        cdn_url = "https://cdn.production.com"
        config = create_production_media_config(cdn_url)

        assert config.base_url == cdn_url
        expected_urls = {
            "development": API_MEDIA_ENDPOINT,
            "testing": TEST_MEDIA_ENDPOINT,
            "production": cdn_url,
        }
        assert config.environment_urls == expected_urls


class TestConstants:
    """Test module constants"""

    def test_api_media_endpoint_constant(self):
        """Test API_MEDIA_ENDPOINT constant"""
        assert API_MEDIA_ENDPOINT == "/api/media"

    def test_test_media_endpoint_constant(self):
        """Test TEST_MEDIA_ENDPOINT constant"""
        assert TEST_MEDIA_ENDPOINT == "/test-media"


class TestIntegration:
    """Test integration scenarios"""

    def test_full_media_field_workflow(self):
        """Test complete workflow of MediaField"""
        # Create field with custom config
        config = MediaConfig(
            base_url="https://cdn.example.com",
            thumbnail_sizes=[200, 400],
            allowed_types=["jpg", "png"],
        )
        field = MediaField(config=config)

        # Test validation
        field.validate("image.jpg")  # Should not raise

        # Test to_python conversion
        python_value = field.to_python("test-image-123")
        assert isinstance(python_value, MediaFieldValue)
        assert python_value.uid == "test-image-123"

        # Test to_database conversion
        db_value = field.to_database(python_value)
        assert db_value == "test-image-123"

        # Test URL generation
        with patch.object(
            field.resolver,
            "resolve_url",
            return_value="https://cdn.example.com/media/test-image-123",
        ):
            assert python_value.url == "https://cdn.example.com/media/test-image-123"

    def test_environment_detection_integration(self):
        """Test environment-specific URL resolution"""
        config = MediaConfig(
            environment_urls={
                "development": "/dev-media",
                "production": "https://prod-cdn.com",
            }
        )

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            resolver = MediaUrlResolver(config)
            url = resolver.resolve_url("test-123")
            assert url == "/dev-media/media/test-123"

    def test_thumbnail_generation_integration(self):
        """Test thumbnail URL generation with various sizes"""
        config = MediaConfig(
            base_url="https://images.com",
            thumbnail_sizes=[150, 300, 600],
            thumbnail_suffix="_thumb",
        )
        field = MediaField(config=config)
        field_value = field.to_python("photo-abc")

        # Mock the resolver to return predictable URLs
        with patch.object(field.resolver, "resolve_url") as mock_resolve:
            mock_resolve.side_effect = (
                lambda uid, **kwargs: f"https://images.com/media/{uid}"
            )

            base_url = field_value.url
            assert "photo-abc" in base_url

            mock_resolve.assert_called_with("photo-abc")
