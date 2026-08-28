---
name: plan-work-package
description: Turn an approved repository plan into one closed qa-toolkit work-package task only when the user explicitly asks to prepare structured work.
---

# Plan Work Package

Use the enrolled repository's `qat-work-*` utilities. Do not invent state in Markdown.

- Confirm the exact repository, issue, remote, base branch and SHA, implementation branch, task ID, allowed paths, validation argv, proof level, and final Conventional Commit subject.
- Keep the accepted plan and current task as bounded human input files. Pass every authoritative field explicitly to `qat work init`.
- Use one active task. For a later task, require the prior task to be complete and increment `plan_revision`.
- Do not create an issue, branch, commit, push, or pull request unless the user authorized that external mutation.
- End by reporting `qat work status`. Never substitute a prose plan for `.git/qat/work/<id>/state.json`.
