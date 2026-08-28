---
name: execute-work-item
description: Implement and finish one staged qa-toolkit work item within its allowed paths when the user explicitly asks to execute that exact task.
---

# Execute Work Item

Load `qat work status` before editing. Treat its current task, allowed paths, validation argv, and final subject as authoritative.

Implement only that task. Do not change package identity or edit JSON state manually. Run `qat work finish` after the implementation is ready. It runs stored argv commands, retains full local output, amends the provisional commit, and exact-lease publishes the result.

If validation fails, leave the provisional commit and worktree changes for repair. If publication is interrupted, use `qat work reconcile`. Do not improvise a force push. Post a report with `qat work report` and `qat agent github pr-comment` only when remote reporting is authorized.
