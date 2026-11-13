# Project workflow

The user requests automatic GitHub synchronization after completed code changes.

- Repository: https://github.com/Priscillacuy/CWdiary.git
- After completing each requested change and its appropriate validation, commit the relevant changes and push to the configured upstream branch. This is already authorized; do not ask again for routine commits/pushes.
- Keep the user's unrelated edits intact. Never force-push or rewrite shared history. If remote history changes, fetch and reconcile safely before pushing.
- Never commit credentials, `.env`, private diaries/account databases, local caches, or personal screenshots/QA captures. Local `docs/` and `design-qa.md` are excluded for this reason.
- If authentication or remote permissions prevent synchronization, retain the local commit and report the specific blocker truthfully.
- Continue using the selected warm Product Design style and verify frontend changes in the actual frontend.

This workflow applies after agent work; it is not a background file watcher.
