"""
Kinglet 1.4.0 Fine-Grained Authorization (FGA) Example

Complete example showing all authorization patterns including admin override.
"""

from kinglet import Response, Router
from kinglet.authz import (
    allow_public_or_owner,
    d1_load_owner_public,
    r2_media_owner,
    require_auth,
    require_owner,
    require_participant,
)

router = Router()

# ============================================================================
# BASIC AUTHENTICATION - User must be logged in
# ============================================================================


@router.get("/profile")
@require_auth
async def get_profile(req):
    """Protected endpoint - requires valid JWT token"""
    user = req.state.user  # {"id": "user-123", "claims": {...}}
    return {"user_id": user["id"], "email": user["claims"].get("email")}


# ============================================================================
# PUBLIC OR OWNER ACCESS - Public resources visible to all, private to owner
# ============================================================================


@router.get("/posts/{post_id}")
@allow_public_or_owner(
    lambda req, pid: d1_load_owner_public(req.env.DB, "posts", pid),
    id_param="post_id",
    forbidden_as_404=True,  # Hide private posts from non-owners (404 instead of 403)
)
async def get_post(req, obj):
    """
    Public posts: Anyone can view
    Private posts: Only owner can view
    obj = {"owner_id": "user-123", "public": True/False}
    """
    post_id = req.path_param("post_id")

    # Load post data
    post = (
        await req.env.DB.prepare("SELECT * FROM posts WHERE id=?").bind(post_id).first()
    )

    # Add owner-only fields if viewer is owner
    if (
        hasattr(req, "state")
        and req.state.user
        and obj["owner_id"] == req.state.user["id"]
    ):
        post["draft_notes"] = "Owner can see draft notes"
        post["analytics"] = {"views": 1234, "likes": 56}

    return {"post": post}


# ============================================================================
# OWNER-ONLY WITH ADMIN OVERRIDE - Owner or admin can access
# ============================================================================


@router.delete("/posts/{post_id}")
@require_owner(
    lambda req, pid: d1_load_owner_public(req.env.DB, "posts", pid),
    id_param="post_id",
    allow_admin_env="ADMIN_IDS",  # ← Admin override via environment variable
)
async def delete_post(req, obj):
    """
    Delete post - only owner can delete their own posts
    BUT admins (listed in ADMIN_IDS env var) can delete ANY post

    Set in wrangler.toml:
    [vars]
    ADMIN_IDS = "admin-user-1,admin-user-2,support-user-3"
    """
    post_id = req.path_param("post_id")

    # Log who is deleting (owner or admin)
    user_id = req.state.user["id"]
    is_admin = user_id != obj["owner_id"]  # Different from owner = must be admin

    await req.env.DB.prepare("DELETE FROM posts WHERE id=?").bind(post_id).run()

    return {
        "deleted": True,
        "post_id": post_id,
        "deleted_by": "admin" if is_admin else "owner",
        "user_id": user_id,
    }


# ============================================================================
# PARTICIPANT ACCESS - Multiple users can access (e.g., conversations)
# ============================================================================


async def load_chat_participants(req, chat_id):
    """Load all participants in a chat conversation"""
    rows = (
        await req.env.DB.prepare("SELECT user_id FROM chat_members WHERE chat_id=?")
        .bind(chat_id)
        .all()
    )
    return {str(row["user_id"]) for row in rows}


@router.get("/chats/{chat_id}/messages")
@require_participant(
    load_chat_participants,
    id_param="chat_id",
    allow_admin_env="ADMIN_IDS",  # ← Admins can view any chat for moderation
)
async def get_chat_messages(req):
    """
    Only chat participants can read messages
    Admins can also access for moderation purposes
    """
    chat_id = req.path_param("chat_id")

    messages = (
        await req.env.DB.prepare(
            "SELECT * FROM messages WHERE chat_id=? ORDER BY created_at"
        )
        .bind(chat_id)
        .all()
    )

    return {"messages": messages}


# ============================================================================
# R2 MEDIA WITH OWNERSHIP - Media files with owner metadata
# ============================================================================


@router.post("/media/upload")
@require_auth
async def upload_media(req):
    """Upload media with owner metadata for FGA"""
    body = await req.body()
    media_id = __import__("uuid").uuid4().hex
    user_id = req.state.user["id"]

    # Store in R2 with owner metadata
    await req.env.STORAGE.put(
        media_id,
        body,
        {
            "httpMetadata": {
                "contentType": req.header("content-type", "application/octet-stream")
            },
            "customMetadata": {
                "owner_id": user_id,  # ← Critical for FGA
                "uploaded_at": str(__import__("time").time()),
            },
        },
    )

    return {"media_id": media_id, "owner": user_id}


@router.get("/media/{media_id}")
@allow_public_or_owner(
    lambda req, mid: r2_media_owner(req.env, "STORAGE", mid), id_param="media_id"
)
async def get_media(req, obj):
    """
    Serve media based on ownership
    obj = {"owner_id": "user-123", "public": False}  # R2 media default private
    """
    media_id = req.path_param("media_id")
    media = await req.env.STORAGE.get(media_id)

    if not media:
        return Response({"error": "not found"}, status=404)

    # Set cache headers based on ownership
    headers = {
        "Content-Type": media.httpMetadata.get(
            "contentType", "application/octet-stream"
        )
    }

    if obj.get("public"):
        headers["Cache-Control"] = "public, max-age=86400"
    else:
        headers["Cache-Control"] = "private, no-cache"

    return Response(media.body, status=200, headers=headers)


# ============================================================================
# COMPLEX SCENARIO - Booking system with owner, renter, and admin access
# ============================================================================


async def load_booking_participants(req, booking_id):
    """Owner of listing + renter can access booking"""
    result = (
        await req.env.DB.prepare("""
        SELECT b.renter_id, l.owner_id
        FROM bookings b
        JOIN listings l ON b.listing_id = l.id
        WHERE b.id = ?
    """)
        .bind(booking_id)
        .first()
    )

    if not result:
        return set()

    return {str(result["renter_id"]), str(result["owner_id"])}


@router.get("/bookings/{booking_id}")
@require_participant(
    load_booking_participants,
    id_param="booking_id",
    allow_admin_env="ADMIN_IDS",  # ← Support team can access for dispute resolution
)
async def get_booking(req):
    """
    Booking details visible to:
    - Listing owner (property owner)
    - Renter (person who booked)
    - Admin/Support (for disputes)
    """
    booking_id = req.path_param("booking_id")

    booking = (
        await req.env.DB.prepare("""
        SELECT b.*, l.title as listing_title,
               u1.name as renter_name, u2.name as owner_name
        FROM bookings b
        JOIN listings l ON b.listing_id = l.id
        JOIN users u1 ON b.renter_id = u1.id
        JOIN users u2 ON l.owner_id = u2.id
        WHERE b.id = ?
    """)
        .bind(booking_id)
        .first()
    )

    return {"booking": booking}


# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

"""
Required environment variables in wrangler.toml:

[vars]
JWT_SECRET = "your-secret-key-change-in-production"
ADMIN_IDS = "admin-user-uuid-1,admin-user-uuid-2,support-user-uuid-3"

[env.production.vars]
JWT_SECRET = "production-secret-from-secrets-manager"
ADMIN_IDS = "prod-admin-1,prod-admin-2"

Admin override allows specified users to bypass ownership checks for:
- Deleting inappropriate content
- Accessing data for support/moderation
- Resolving disputes
- Emergency access

The admin list is cached by the Workers runtime, so changes require redeployment.
"""
