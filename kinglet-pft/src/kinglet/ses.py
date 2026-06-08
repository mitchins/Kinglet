"""
Amazon SES Email Support for Kinglet

Send emails via Amazon SES from Cloudflare Workers.
Zero JS files required - signing uses JS crypto directly from Python.

Setup - just configure wrangler.toml:

    [vars]
    AWS_REGION = "us-east-1"
    AWS_ACCESS_KEY_ID = "AKIA..."

    # For production: wrangler secret put AWS_SECRET_ACCESS_KEY

Usage:
    from kinglet.ses import send_email

    result = await send_email(
        request.env,
        from_email="noreply@example.com",
        to=["user@example.com"],
        subject="Hello",
        body_text="Plain text body",
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


@dataclass
class EmailResult:
    """Result of send_email operation"""

    success: bool
    message_id: str | None = None
    error: str | None = None


async def send_email(
    env,
    *,
    from_email: str,
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    reply_to: list[str] | None = None,
    region: str | None = None,
) -> EmailResult:
    """
    Send email via Amazon SES.

    Args:
        env: Cloudflare Workers environment with AWS credentials
        from_email: Sender email address (must be verified in SES)
        to: List of recipient email addresses
        subject: Email subject
        body_text: Plain text email body
        body_html: Optional HTML email body
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        reply_to: Optional reply-to addresses
        region: AWS region (defaults to env.AWS_REGION)

    Returns:
        EmailResult with success status and message_id or error
    """
    try:
        # Get AWS config from environment
        aws_region = region or _get_env_var(env, "AWS_REGION")
        access_key = _get_env_var(env, "AWS_ACCESS_KEY_ID")
        secret_key = _get_env_var(env, "AWS_SECRET_ACCESS_KEY")

        if not aws_region or not access_key or not secret_key:
            return EmailResult(
                success=False,
                error="Missing AWS credentials (AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)",
            )

        # Build SES API request
        url = f"https://email.{aws_region}.amazonaws.com/v2/email/outbound-emails"

        # Build destination
        destination: dict[str, Any] = {"ToAddresses": to}
        if cc:
            destination["CcAddresses"] = cc
        if bcc:
            destination["BccAddresses"] = bcc

        # Build content
        body_content: dict[str, Any] = {"Text": {"Data": body_text, "Charset": "UTF-8"}}
        if body_html:
            body_content["Html"] = {"Data": body_html, "Charset": "UTF-8"}

        payload = {
            "FromEmailAddress": from_email,
            "Destination": destination,
            "Content": {
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body_content,
                }
            },
        }

        if reply_to:
            payload["ReplyToAddresses"] = reply_to

        body = json.dumps(payload)

        # Sign the request using JS crypto
        signed_headers = await _sign_aws_request(
            "POST", url, aws_region, "ses", access_key, secret_key, body
        )

        # Make the request
        import js

        response = await js.fetch(
            url,
            js.Object.fromEntries(
                js.Array.of(
                    js.Array.of("method", "POST"),
                    js.Array.of("headers", signed_headers),
                    js.Array.of("body", body),
                )
            ),
        )

        response_text = await response.text()

        if response.ok:
            try:
                result = json.loads(str(response_text))
                return EmailResult(success=True, message_id=result.get("MessageId"))
            except json.JSONDecodeError:
                return EmailResult(success=True, message_id=None)
        else:
            return EmailResult(success=False, error=f"SES error: {response_text}")

    except Exception as e:
        return EmailResult(success=False, error=str(e))


async def _sign_aws_request(
    method: str,
    url: str,
    region: str,
    service: str,
    access_key: str,
    secret_key: str,
    body: str,
) -> Any:
    """
    Sign AWS request using SigV4.
    Uses JS crypto.subtle directly from Python - no external JS file needed.
    """
    import js

    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"

    # Timestamps
    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Hash the payload
    payload_hash = await _sha256_hex(body)

    # Canonical headers
    canonical_headers = (
        f"content-type:application/json\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

    # Canonical request
    canonical_request = "\n".join(
        [method, path, "", canonical_headers, signed_headers, payload_hash]
    )

    # String to sign
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    canonical_request_hash = await _sha256_hex(canonical_request)

    string_to_sign = "\n".join(
        [algorithm, amz_date, credential_scope, canonical_request_hash]
    )

    # Derive signing key (chained HMAC)
    k_date = await _hmac_sha256_key(f"AWS4{secret_key}", date_stamp)
    k_region = await _hmac_sha256_buf(k_date, region)
    k_service = await _hmac_sha256_buf(k_region, service)
    k_signing = await _hmac_sha256_buf(k_service, "aws4_request")

    # Calculate signature
    signature = await _hmac_sha256_hex(k_signing, string_to_sign)

    # Build authorization header
    authorization = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    # Return as JS object for fetch
    return js.Object.fromEntries(
        js.Array.of(
            js.Array.of("Content-Type", "application/json"),
            js.Array.of("Host", host),
            js.Array.of("X-Amz-Date", amz_date),
            js.Array.of("X-Amz-Content-Sha256", payload_hash),
            js.Array.of("Authorization", authorization),
        )
    )


async def _sha256_hex(message: str) -> str:
    """SHA-256 hash using JS crypto.subtle"""
    import js

    encoder = js.TextEncoder.new()
    data = encoder.encode(message)
    hash_buffer = await js.crypto.subtle.digest("SHA-256", data)
    return _buffer_to_hex(hash_buffer)


async def _hmac_sha256_key(key_str: str, message: str):
    """HMAC-SHA256 with string key, returns ArrayBuffer"""
    import js

    encoder = js.TextEncoder.new()
    key_data = encoder.encode(key_str)
    message_data = encoder.encode(message)

    algorithm = js.Object.fromEntries(
        js.Array.of(js.Array.of("name", "HMAC"), js.Array.of("hash", "SHA-256"))
    )

    crypto_key = await js.crypto.subtle.importKey(
        "raw", key_data, algorithm, False, js.Array.of("sign")
    )

    return await js.crypto.subtle.sign("HMAC", crypto_key, message_data)


async def _hmac_sha256_buf(key_buffer, message: str):
    """HMAC-SHA256 with ArrayBuffer key, returns ArrayBuffer"""
    import js

    encoder = js.TextEncoder.new()
    message_data = encoder.encode(message)

    algorithm = js.Object.fromEntries(
        js.Array.of(js.Array.of("name", "HMAC"), js.Array.of("hash", "SHA-256"))
    )

    crypto_key = await js.crypto.subtle.importKey(
        "raw", key_buffer, algorithm, False, js.Array.of("sign")
    )

    return await js.crypto.subtle.sign("HMAC", crypto_key, message_data)


async def _hmac_sha256_hex(key_buffer, message: str) -> str:
    """HMAC-SHA256 returning hex string"""
    result = await _hmac_sha256_buf(key_buffer, message)
    return _buffer_to_hex(result)


def _buffer_to_hex(buffer) -> str:
    """Convert JS ArrayBuffer to hex string"""
    import js

    uint8 = js.Uint8Array.new(buffer)
    # Convert to Python bytes via .to_py() then to hex
    # Pyodide JsProxy objects need .to_py() for iteration
    py_bytes = bytes(uint8.to_py())
    return py_bytes.hex()


def _get_env_var(env, name: str) -> str | None:
    """Get environment variable from Workers env object"""
    if env is None:
        return None

    # Try direct attribute access
    if hasattr(env, name):
        value = getattr(env, name)
        if value is not None and str(value) != "undefined":
            return str(value)

    # Try dict-like access
    try:
        value = env[name]
        if value is not None and str(value) != "undefined":
            return str(value)
    except (KeyError, TypeError):
        pass

    return None
