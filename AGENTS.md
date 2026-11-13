# Project workflow

The user requests automatic GitHub synchronization after completed code changes.

- Repository: https://github.com/Priscillacuy/CWdiary.git
- After completing each requested change and its appropriate validation, commit the relevant changes and push to the configured upstream branch. This is already authorized; do not ask again for routine commits/pushes.
- Keep the user's unrelated edits intact. Never force-push or rewrite shared history. If remote history changes, fetch and reconcile safely before pushing.
- Never commit credentials, `.env`, private diaries/account databases, local caches, or personal screenshots/QA captures. Local `docs/` and `design-qa.md` are excluded for this reason.
- If authentication or remote permissions prevent synchronization, retain the local commit and report the specific blocker truthfully.
- If command-line authentication is unavailable but the GitHub connector is connected, use its Git blob/tree/commit/ref tools to synchronize the exact tracked tree. Verify the remote result and reconcile local history only after checking that the trees match and the working directory is clean.
- Continue using the selected warm Product Design style and verify frontend changes in the actual frontend.

This workflow applies after agent work; it is not a background file watcher.

## Production deployment

- Vercel project `cwdiary`, team `p-ri-s`, production URL https://cwdiary-gray.vercel.app/.
- Completed, validated changes should be pushed to `main` and their automatic Vercel deployment checked. Do not claim the application is fully live until runtime and persistent storage checks pass.
- Production uses the WSGI entrypoint and Turso environment variables; never use disposable `/tmp` SQLite for production user accounts or diaries.
- Do not publish the local `instance/` data or `.env`; production secrets belong only in Vercel encrypted environment variables.
