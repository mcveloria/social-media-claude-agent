# social-poster

Publishes **only human-approved** posts, **exactly as written**, on a schedule to:

- Your own Instagram (Business/Creator), LinkedIn profile and Facebook Page

## How it stays safe

| Rule | How it is enforced |
|---|---|
| Nothing posts unless approved | Only `status: approved` posts are considered; the marketing agent's `add` always creates a **draft** and discards any approval fields. |
| Approved content can't change | Approval stores a SHA-256 of text, per-platform text, media, platforms and schedule. If anything differs at publish time the post is **blocked**, not posted. |
| No edits by the tool | Text is sent verbatim. Over-limit text is rejected at validation, never truncated. (LinkedIn markup characters are backslash-escaped so they display literally.) |
| No surprise posts | Dry-run by default; live needs `--live` / repo variable `LIVE_PUBLISHING=true`. |
| No stale posts | Posts more than `MAX_LATE_MINUTES` (default 120) late are marked `missed`, not posted. |
| No duplicates | Per-platform result is recorded before and after each call; failed/in-flight platforms are never auto-retried. |

## Workflow

1. **Marketing agent** writes a JSON file (see `examples-draft.json`) and runs `python -m socialposter add file.json`, then commits to `queue/` on a branch / PR.
2. **You** review and approve: `python -m socialposter approve <id> --by yourname` (shows the exact content, asks you to type the id). Commit the change.
3. **GitHub Action** runs every 15 min, publishes approved posts that are due, and commits the results back.

Other commands: `list`, `show <id>`, `reject <id>`, `cancel <id>`, `run` (dry-run).

Make approval meaningful: protect `main` (require PR + CODEOWNERS review, owner only) so the agent can't merge its own approvals, and set your username in `.github/CODEOWNERS`.

## Setup

1. Repo **Settings → Secrets and variables → Actions → Secrets**: `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID`, `INSTAGRAM_ACCESS_TOKEN`, `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_ID`.
2. Variables: `LIVE_PUBLISHING=true` once a dry run looks right.
3. Credentials you need (one-time, in your Meta/LinkedIn developer accounts):
   - **Meta**: Instagram must be a Business/Creator account linked to your Facebook Page. App with `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`. Use a long-lived Page token.
   - **LinkedIn**: app with "Share on LinkedIn" (`w_member_social`); personal-profile tokens expire (~60 days) and must be refreshed.
4. Instagram requires media (image or video) at a public `https://` URL. Instagram/Facebook/LinkedIn video is limited here to Instagram Reels.

## Local use

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m socialposter run          # dry run
```
