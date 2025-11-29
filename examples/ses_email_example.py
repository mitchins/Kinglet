"""
SES Email Example - Send emails via Amazon SES from Cloudflare Workers

This example demonstrates sending emails using Amazon SES with Kinglet.
No JS files required - just configure wrangler.toml and go!

SETUP:
1. Configure wrangler.toml with AWS credentials
2. Verify your sender email in SES console

wrangler.toml:
    [vars]
    AWS_REGION = "us-east-1"
    AWS_ACCESS_KEY_ID = "AKIA..."

    # For production, use secrets:
    # wrangler secret put AWS_SECRET_ACCESS_KEY
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from kinglet import Kinglet, Response

app = Kinglet()


@app.post("/send-email")
async def send_email_endpoint(request):
    """
    Send an email via SES

    POST /send-email
    {
        "to": ["recipient@example.com"],
        "subject": "Hello",
        "body": "Email body text",
        "html": "<h1>Optional HTML</h1>"
    }
    """
    from kinglet.ses import send_email

    data = await request.json()

    # Validate required fields
    if not data.get("to") or not data.get("subject") or not data.get("body"):
        return Response.error(
            "Missing required fields: to, subject, body",
            status=400,
            request_id=request.request_id,
        )

    result = await send_email(
        request.env,
        from_email="noreply@yourdomain.com",  # Must be verified in SES
        to=data["to"],
        subject=data["subject"],
        body_text=data["body"],
        body_html=data.get("html"),
    )

    if result.success:
        return {"success": True, "message_id": result.message_id}
    else:
        return Response.error(result.error or "Failed to send email", status=500)


@app.post("/notify")
async def send_notification(request):
    """
    Example: Send notification email with template

    POST /notify
    {
        "user_email": "user@example.com",
        "user_name": "John",
        "event": "signup"
    }
    """
    from kinglet.ses import send_email

    data = await request.json()
    user_email = data.get("user_email")
    user_name = data.get("user_name", "User")
    event = data.get("event", "notification")

    # Simple template
    templates = {
        "signup": {
            "subject": f"Welcome, {user_name}!",
            "body": f"Hi {user_name},\n\nWelcome to our platform!\n\nBest regards,\nThe Team",
            "html": f"<h1>Welcome, {user_name}!</h1><p>Welcome to our platform!</p>",
        },
        "password_reset": {
            "subject": "Password Reset Request",
            "body": f"Hi {user_name},\n\nClick the link to reset your password.\n\nBest regards,\nThe Team",
            "html": f"<h1>Password Reset</h1><p>Hi {user_name}, click the link to reset.</p>",
        },
    }

    template = templates.get(event, templates["signup"])

    result = await send_email(
        request.env,
        from_email="noreply@yourdomain.com",
        to=[user_email],
        subject=template["subject"],
        body_text=template["body"],
        body_html=template["html"],
    )

    return {"sent": result.success, "error": result.error}


# Workers entry point
async def on_fetch(request, env):
    return await app(request, env)


if __name__ == "__main__":
    print("SES Email Example")
    print("=" * 40)
    print()
    print("This example requires:")
    print("1. AWS credentials in wrangler.toml")
    print("2. The aws-sigv4.js helper (see examples/aws-sigv4.js)")
    print("3. Verified sender email in SES")
    print()
    print("Deploy with: wrangler deploy")
