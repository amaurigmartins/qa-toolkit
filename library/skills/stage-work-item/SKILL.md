---
name: stage-work-item
description: Stage and bind one accepted qa-toolkit work item; use when the user explicitly authorizes its branch, provisional commit, publication, and draft PR.
---

# Stage Work Item

Operate only on an already initialized package.

- Run `qat work status` and confirm clean exact-parent state.
- With publication authorization, run `qat work stage`. This creates the one provisional commit and publishes it without implementing the task.
- Create the draft PR with `qat agent github pr-create` only when authorized, then bind its exact number with `qat work bind`.
- Stop on repository, branch, parent, remote, issue, or PR drift. Do not bypass hooks or replace exact-lease behavior.
- Report the provisional SHA and bound PR from structured status.

