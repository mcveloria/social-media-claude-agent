"""Post schema, validation and the content hash that locks approved content."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

PLATFORMS = ("instagram", "linkedin", "facebook")
CHAR_LIMITS = {"instagram": 2200, "linkedin": 3000, "facebook": 63206}
STATUSES = ("draft", "approved", "published", "partial", "failed", "missed", "cancelled", "rejected")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ValidationError(ValueError):
    pass


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValidationError(f"scheduled_at must include a timezone (e.g. 2026-11-02T14:00:00Z): {value!r}")
    return dt.astimezone(timezone.utc)


def text_for(post: dict, platform: str) -> str:
    """Exact text that is published to a platform. Never altered."""
    return post.get("platform_text", {}).get(platform, post["text"])


def content_hash(post: dict) -> str:
    """Hash of everything that gets published or decides where/when. Approval is bound to this."""
    payload = {
        "platforms": sorted(post["platforms"]),
        "text": post["text"],
        "platform_text": post.get("platform_text", {}),
        "media": post.get("media"),
        "scheduled_at": parse_time(post["scheduled_at"]).isoformat(),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate(post: dict) -> None:
    if not ID_RE.match(str(post.get("id", ""))):
        raise ValidationError("id must be 1-64 chars: letters, digits, _ or -")
    platforms = post.get("platforms")
    if not platforms or any(p not in PLATFORMS for p in platforms) or len(set(platforms)) != len(platforms):
        raise ValidationError(f"platforms must be a non-empty unique subset of {PLATFORMS}")
    if not isinstance(post.get("text"), str) or not post["text"].strip():
        raise ValidationError("text is required")
    extra = set(post.get("platform_text", {})) - set(platforms)
    if extra:
        raise ValidationError(f"platform_text for platforms not targeted: {sorted(extra)}")
    parse_time(post.get("scheduled_at", ""))
    media = post.get("media")
    if media is not None:
        if media.get("type") not in ("image", "video") or not str(media.get("url", "")).startswith("https://"):
            raise ValidationError("media must be {type: image|video, url: https://...}")
    if "instagram" in platforms and not media:
        raise ValidationError("instagram posts require media (image or video)")
    if media and media["type"] == "video" and "linkedin" in platforms:
        raise ValidationError("video is not supported for linkedin in this tool; remove linkedin or use an image")
    if media and media["type"] == "video" and "facebook" in platforms:
        raise ValidationError("video is not supported for facebook in this tool; remove facebook or use an image")
    for p in platforms:
        if len(text_for(post, p)) > CHAR_LIMITS[p]:
            raise ValidationError(f"text exceeds {p} limit of {CHAR_LIMITS[p]} characters (it is never truncated)")
