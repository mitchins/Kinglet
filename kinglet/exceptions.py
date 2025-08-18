"""
Kinglet Exception Classes
"""

class HTTPError(Exception):
    """HTTP error with status code and message"""
    def __init__(self, status_code: int, message: str, request_id: str = None):
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        super().__init__(message)

class GeoRestrictedError(HTTPError):
    """Geographic restriction error"""
    def __init__(self, country_code: str, allowed_countries: list = None, request_id: str = None):
        if allowed_countries:
            message = f"Access denied from {country_code}. Allowed: {', '.join(allowed_countries)}"
        else:
            message = f"Access denied from {country_code}"
        super().__init__(451, message, request_id)  # HTTP 451 Unavailable For Legal Reasons
        self.country_code = country_code
        self.allowed_countries = allowed_countries or []

class DevOnlyError(HTTPError):
    """Development-only endpoint accessed in production"""
    def __init__(self, request_id: str = None):
        message = "This endpoint is only available in development mode"
        super().__init__(403, message, request_id)
