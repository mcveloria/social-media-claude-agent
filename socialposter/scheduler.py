"""Publishes due posts. The only path to a live post, and it is gated on human approval."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import store
from .models import content_hash, parse_time, text_for, validate, ValidationError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def check_approved(post: dict) -> str | None:
    """Return None if the post may be published, else the reason it is blocked."""
    if post.get("status") != "approved":
        return f"status is {post.get('status')!r}, not 'approved'"
    appr = post.get("approval") or {}
    if not appr.get("approved_by") or not appr.get("content_hash"):
        return "missing approval record"
    try:
        validate(post)
        if content_hash(post) != appr["content_hash"]:
            return "content changed after approval; re-approve to publish"
    except ValidationError as e:
        return f"invalid post: {e}"
    return None


def run(publishers: dict, live: bool, queue_dir: Path | None = None, now: datetime | None = None, log=print) -> int:
    """Returns the number of problems (blocked/failed posts) so callers can surface them."""
    now = now or now_utc()
    max_late = timedelta(minutes=int(os.environ.get("MAX_LATE_MINUTES", "120")))
    problems = 0
    for post in store.load_all(queue_dir):
        if post.get("status") != "approved":
            continue
        pid = post["id"]
        try:
            due_at = parse_time(post["scheduled_at"])
        except ValidationError as e:
            log(f"[BLOCKED] {pid}: {e}")
            problems += 1
            continue
        if due_at > now:
            continue
        reason = check_approved(post)
        if reason:
            log(f"[BLOCKED] {pid}: {reason}")
            problems += 1
            continue
        if now - due_at > max_late:
            log(f"[MISSED]  {pid}: {now - due_at} past schedule, not posting stale content")
            if live:
                post["status"] = "missed"
                store.save(post, queue_dir)
            continue
        results = post.setdefault("results", {})
        for platform in post["platforms"]:
            if platform in results:  # published, failed or in-flight: never auto-retry, avoids duplicates
                continue
            text = text_for(post, platform)
            if not live:
                log(f"[DRY-RUN] {pid} -> {platform}: would post {len(text)} chars" + (f" + {post['media']['type']}" if post.get("media") else ""))
                continue
            results[platform] = {"state": "publishing", "at": now_utc().isoformat()}
            store.save(post, queue_dir)
            try:
                out = publishers[platform].publish(text, post.get("media"))
                results[platform] = {"state": "published", "at": now_utc().isoformat(), **out}
                log(f"[POSTED]  {pid} -> {platform} {out.get('url') or out.get('id')}")
            except Exception as e:  # noqa: BLE001 - record any failure against the platform
                results[platform] = {"state": "failed", "at": now_utc().isoformat(), "error": str(e)[:500]}
                log(f"[FAILED]  {pid} -> {platform}: {e}")
                problems += 1
            store.save(post, queue_dir)
        if live:
            states = [results.get(p, {}).get("state") for p in post["platforms"]]
            if all(s == "published" for s in states):
                post["status"] = "published"
            elif any(s == "published" for s in states):
                post["status"] = "partial"
            elif all(s in ("failed", "published") for s in states):
                post["status"] = "failed"
            store.save(post, queue_dir)
    return problems
