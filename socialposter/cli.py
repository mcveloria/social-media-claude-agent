"""CLI: add (agent), approve/reject (human), run (scheduler)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import store
from .models import ValidationError, content_hash, text_for, validate
from .publishers import default_publishers
from .scheduler import now_utc, run

AGENT_FIELDS = ("id", "platforms", "text", "platform_text", "media", "scheduled_at")


def cmd_add(args) -> int:
    """Marketing agent hand-off. Always creates a DRAFT; any approval/status/results in the input is discarded."""
    raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        post = {k: item[k] for k in AGENT_FIELDS if k in item}
        post["status"] = "draft"
        validate(post)
        if store.path_for(post["id"]).exists():
            raise ValidationError(f"{post['id']} already exists; use a new id (published/approved posts are never overwritten)")
        store.save(post)
        print(f"drafted {post['id']} (needs human approval)")
    return 0


def cmd_list(args) -> int:
    for p in store.load_all():
        print(f"{p['id']:<30} {p['status']:<10} {p['scheduled_at']}  {','.join(p['platforms'])}")
    return 0


def cmd_show(args) -> int:
    post = store.load(args.id)
    for platform in post["platforms"]:
        print(f"--- {platform} ---\n{text_for(post, platform)}")
    print(f"--- media ---\n{post.get('media')}\n--- scheduled ---\n{post['scheduled_at']}\n--- status ---\n{post['status']}")
    return 0


def cmd_approve(args) -> int:
    post = store.load(args.id)
    if post["status"] != "draft":
        raise ValidationError(f"only drafts can be approved (status is {post['status']})")
    validate(post)
    cmd_show(args)
    if not args.yes and input(f"\nType the post id to approve exactly this content: ").strip() != post["id"]:
        print("not approved")
        return 1
    post["status"] = "approved"
    post["approval"] = {"approved_by": args.by, "approved_at": now_utc().isoformat(), "content_hash": content_hash(post)}
    store.save(post)
    print(f"approved {post['id']} by {args.by}")
    return 0


def _set_status(args, status: str, allowed: tuple) -> int:
    post = store.load(args.id)
    if post["status"] not in allowed:
        raise ValidationError(f"cannot move {post['status']} -> {status}")
    post["status"] = status
    post.pop("approval", None)
    store.save(post)
    print(f"{status} {post['id']}")
    return 0


REQUIRED_ENV = {
    "facebook": ("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN"),
    "instagram": ("INSTAGRAM_BUSINESS_ACCOUNT_ID", "INSTAGRAM_ACCESS_TOKEN"),
    "linkedin": ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_ID"),
}


def cmd_doctor(args) -> int:
    """Offline setup check: queue validity and which platform credentials are present (values never printed)."""
    import os
    bad = 0
    try:
        posts = store.load_all()
        store.validate_all()
        counts = {}
        for p in posts:
            counts[p["status"]] = counts.get(p["status"], 0) + 1
        print(f"queue ok: {len(posts)} posts {counts}")
    except (ValidationError, json.JSONDecodeError) as e:
        print(f"queue problem: {e}")
        bad += 1
    for platform, names in REQUIRED_ENV.items():
        missing = [n for n in names if not os.environ.get(n)]
        print(f"{platform:<10} {'credentials set' if not missing else 'missing ' + ', '.join(missing)}")
        bad += bool(missing)
    return 1 if bad else 0


def cmd_run(args) -> int:
    store.validate_all()
    publishers = default_publishers() if args.live else {}
    problems = run(publishers, live=args.live)
    return 1 if problems else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="socialposter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", help="add draft post(s) from a JSON file (marketing agent)"); p.add_argument("file"); p.set_defaults(fn=cmd_add)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("approve", help="human approval of a draft"); p.add_argument("id"); p.add_argument("--by", required=True); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("reject"); p.add_argument("id"); p.set_defaults(fn=lambda a: _set_status(a, "rejected", ("draft", "approved")))
    p = sub.add_parser("cancel", help="withdraw an approved post before it goes out"); p.add_argument("id"); p.set_defaults(fn=lambda a: _set_status(a, "cancelled", ("draft", "approved")))
    sub.add_parser("doctor", help="check setup (no network, no posting)").set_defaults(fn=cmd_doctor)
    p = sub.add_parser("run", help="publish approved posts that are due (dry-run unless --live)"); p.add_argument("--live", action="store_true"); p.set_defaults(fn=cmd_run)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (ValidationError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
