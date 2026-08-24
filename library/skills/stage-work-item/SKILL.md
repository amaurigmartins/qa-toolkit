---
name: stage-work-item
description: Stage and bind one accepted qa-toolkit work item when the user explicitly authorises its branch, provisional commit, publication, and draft PR.
---

# Stage Work Item

Operate only on an already initialised package.

- Run `qat work status` and confirm clean exact-parent state.
- With publication authorization, run `qat work stage`. This creates the one provisional commit and publishes it without implementing the task.
- Create the draft PR with `qat agent github pr-create` only when authorised, then bind its exact number with `qat work bind`.
- Stop on repository, branch, parent, remote, issue, or PR drift. Do not bypass hooks or replace exact-lease behaviour.
- Report the provisional SHA and bound PR from structured status.
