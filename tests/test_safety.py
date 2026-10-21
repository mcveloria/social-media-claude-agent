import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from socialposter import scheduler, store
from socialposter.models import content_hash, validate, ValidationError
from socialposter.publishers import LinkedIn

NOW = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)


class Fake:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []

    def publish(self, text, media):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append(text)
        return {"id": f"{self.name}-1", "url": "https://example.com"}


def make_post(**kw):
    post = {"id": "p1", "platforms": ["instagram", "linkedin", "facebook"], "text": "Hello (world) #launch",
            "media": {"type": "image", "url": "https://example.com/a.jpg"},
            "scheduled_at": "2026-11-02T13:30:00Z", "status": "draft"}
    post.update(kw)
    return post


def approve(post):
    post["status"] = "approved"
    post["approval"] = {"approved_by": "tester", "approved_at": "x", "content_hash": content_hash(post)}
    return post


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.q = Path(self.tmp.name)
        self.pubs = {n: Fake(n) for n in ("instagram", "linkedin", "facebook")}

    def tearDown(self):
        self.tmp.cleanup()

    def run_live(self, now=NOW):
        return scheduler.run(self.pubs, live=True, queue_dir=self.q, now=now, log=lambda *_: None)

    def sent(self):
        return {n: p.sent for n, p in self.pubs.items()}

    def test_draft_is_never_posted(self):
        store.save(make_post(), self.q)
        self.run_live()
        self.assertEqual(self.sent(), {"instagram": [], "linkedin": [], "facebook": []})

    def test_approved_post_is_published_verbatim(self):
        store.save(approve(make_post()), self.q)
        self.assertEqual(self.run_live(), 0)
        self.assertTrue(all(s == ["Hello (world) #launch"] for s in self.sent().values()))
        self.assertEqual(store.load("p1", self.q)["status"], "published")

    def test_edit_after_approval_is_blocked(self):
        post = approve(make_post())
        post["text"] = "Edited text"
        store.save(post, self.q)
        self.assertEqual(self.run_live(), 1)
        self.assertEqual(self.sent(), {"instagram": [], "linkedin": [], "facebook": []})

    def test_schedule_change_after_approval_is_blocked(self):
        post = approve(make_post())
        post["scheduled_at"] = "2026-11-02T13:45:00Z"
        store.save(post, self.q)
        self.assertEqual(self.run_live(), 1)

    def test_status_flipped_without_approval_record_is_blocked(self):
        post = make_post(status="approved")
        store.save(post, self.q)
        self.assertEqual(self.run_live(), 1)
        self.assertEqual(self.sent()["facebook"], [])

    def test_not_due_yet(self):
        store.save(approve(make_post(scheduled_at="2026-11-02T15:00:00Z")), self.q)
        self.run_live()
        self.assertEqual(self.sent()["facebook"], [])

    def test_stale_post_is_missed_not_posted(self):
        store.save(approve(make_post()), self.q)
        self.run_live(now=NOW + timedelta(hours=5))
        self.assertEqual(self.sent()["facebook"], [])
        self.assertEqual(store.load("p1", self.q)["status"], "missed")

    def test_no_duplicate_on_rerun(self):
        store.save(approve(make_post()), self.q)
        self.run_live()
        self.run_live()
        self.assertEqual(len(self.pubs["facebook"].sent), 1)

    def test_failure_is_isolated_and_not_retried(self):
        self.pubs["linkedin"] = Fake("linkedin", fail=True)
        store.save(approve(make_post()), self.q)
        self.assertEqual(self.run_live(), 1)
        self.assertEqual(store.load("p1", self.q)["status"], "partial")
        self.run_live()
        self.assertEqual(len(self.pubs["instagram"].sent), 1)
        self.assertEqual(self.pubs["linkedin"].sent, [])

    def test_dry_run_posts_nothing_and_changes_nothing(self):
        store.save(approve(make_post()), self.q)
        scheduler.run(self.pubs, live=False, queue_dir=self.q, now=NOW, log=lambda *_: None)
        self.assertEqual(self.sent()["facebook"], [])
        self.assertEqual(store.load("p1", self.q)["status"], "approved")

    def test_add_cannot_self_approve(self):
        from socialposter import cli
        f = self.q / "in.json"
        f.write_text(json.dumps(approve(make_post())))
        old = store.QUEUE_DIR
        store.QUEUE_DIR = self.q / "queue"
        try:
            cli.cmd_add(type("A", (), {"file": str(f)}))
            saved = store.load("p1", store.QUEUE_DIR)
        finally:
            store.QUEUE_DIR = old
        self.assertEqual(saved["status"], "draft")
        self.assertNotIn("approval", saved)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            validate(make_post(media=None))  # instagram needs media
        with self.assertRaises(ValidationError):
            validate(make_post(scheduled_at="2026-11-02T13:30:00"))  # no timezone
        with self.assertRaises(ValidationError):
            validate(make_post(text="x" * 2201))  # over instagram limit, never truncated

    def test_linkedin_escape_keeps_hashtags(self):
        self.assertEqual(LinkedIn.escape("a (b) #c *d*"), r"a \(b\) #c \*d\*")


if __name__ == "__main__":
    unittest.main()
