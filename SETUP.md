# Setup guide (for anyone using this agent)

Each person runs **their own copy** with **their own accounts and tokens**. Never share tokens, and never put them in files.

## 1. Get your copy
Click **Use this template → Create a new repository** (or fork it) and choose **Private**. Keep your copy private and do not add collaborators: anyone with write access to your copy can read your tokens.

## 2. Check you have the hidden files
Your copy must contain `.github/workflows/publish.yml`, `.github/CODEOWNERS` and `.gitignore`. They come with the template. If you copied the files by hand, make sure these dot-files are included, because browser uploads often skip them.

## 3. Connect your accounts
| Platform | What you need |
|---|---|
| Facebook Page | Page ID + long-lived Page access token (`pages_manage_posts`, `pages_read_engagement`) |
| Instagram | Business/Creator account linked to that Page; its account ID + access token (`instagram_basic`, `instagram_content_publish`) |
| LinkedIn | App with "Share on LinkedIn" (`w_member_social`); access token + your member ID (tokens expire ~60 days) |

Add them in **Settings → Secrets and variables → Actions → New repository secret**, using the names in `.env.example`. Only add the platforms you use.

## 4. Lock down approval
- Replace `@REPLACE_WITH_YOUR_GITHUB_USERNAME` in `.github/CODEOWNERS` with your GitHub username.
- Settings → Branches → protect `main`: require a pull request and code-owner review. This is what stops anyone else (including a content agent) approving posts.

## 5. Test safely
Actions tab → **publish-approved-posts → Run workflow** with *live* unchecked. Dry run posts nothing and logs what would go out. Locally, `python -m socialposter doctor` checks your setup.

## 6. Go live
Settings → Variables → add `LIVE_PUBLISHING` = `true`.

## Daily use
1. Your content agent/person creates a draft: `python -m socialposter add post.json` and opens a PR.
2. You review, then `python -m socialposter approve <id> --by <you>` and merge.
3. The Action posts it at the scheduled time, exactly as approved.

Pull a post back with `cancel <id>` before its time. Changing an approved post blocks it until you approve again.

## Notes
- Platform rules apply (Meta app review for public use, LinkedIn terms). Using your own accounts in development mode generally works without review.
- Scheduled GitHub Actions can run several minutes late, and GitHub pauses them after 60 days without repo activity.
- Not affiliated with Meta or LinkedIn.
