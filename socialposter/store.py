"""One JSON file per post in queue/. Plain files so every change is reviewable in git."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .models import ValidationError, validate

QUEUE_DIR = Path(os.environ.get("QUEUE_DIR", "queue"))


def path_for(post_id: str, queue_dir: Path | None = None) -> Path:
    return (queue_dir or QUEUE_DIR) / f"{post_id}.json"


def save(post: dict, queue_dir: Path | None = None) -> None:
    queue_dir = queue_dir or QUEUE_DIR
    queue_dir.mkdir(parents=True, exist_ok=True)
    p = path_for(post["id"], queue_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def load(post_id: str, queue_dir: Path | None = None) -> dict:
    p = path_for(post_id, queue_dir)
    if not p.exists():
        raise ValidationError(f"no such post: {post_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_all(queue_dir: Path | None = None) -> list[dict]:
    posts = []
    for p in sorted((queue_dir or QUEUE_DIR).glob("*.json")):
        post = json.loads(p.read_text(encoding="utf-8"))
        if post.get("id") != p.stem:
            raise ValidationError(f"{p.name}: id does not match filename")
        posts.append(post)
    return posts


def validate_all(queue_dir: Path | None = None) -> None:
    for post in load_all(queue_dir):
        validate(post)
