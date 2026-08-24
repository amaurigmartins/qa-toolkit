---
name: run-work-package
description: Advance all already accepted tasks in one qa-toolkit work package; use only when the user explicitly authorizes end-to-end execution of the accepted track.
---

# Run Work Package

Advance one task at a time through initialize, stage, bind, execute, finish, and report. Keep each task in its own provisional/final commit and re-read `qat work status` at every transition.

Do not manufacture unapproved tasks, combine task commits, widen allowed paths, alter validation argv, merge a PR, publish a release, or automate Codex hook trust. Stop when a new human decision or authorization is required. Use `qat work reconcile` after interruption rather than reconstructing state from prose.

