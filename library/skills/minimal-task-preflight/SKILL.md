---
name: minimal-task-preflight
description: Perform an explicit preflight for a repository task using live evidence, the smallest complete design, bounded validation, and no unrelated cleanup. Use only when the user invokes this skill.
---

# Minimal Task Preflight

Use this skill only as a manually requested preflight. Inspect the live repository and the user's
task before proposing safeguards, structure, tests, or compatibility work. Do not create
work-package state, edit files, commit, or publish unless the user separately requests those
actions.

The complete source prompt remains retained outside the ordinary context. Read only exact excerpts
through the supplied reader. Resolve this skill's directory, use it as the working directory, and
run:

```console
python scripts/read_task_sections.py --index references/sections.toml EXCERPT
```

Read each emitted excerpt completely. Do not open the complete source prompt unless the user asks
for an exhaustive reading.

Select excerpts narrowly:

- Start with `task-authority` to reconstruct the task and current repository.
- Use `task-classification` when compatibility, persistence, numerical behavior, performance, or
  an external dependency changes the implementation boundary.
- Use `task-minimal-design` for ownership, extension placement, change amplification, or a
  complexity decision.
- Use `task-dependencies` only for dependency, process-boundary, API, persistence, or error-model
  work.
- Use `task-tests` when deciding proof scope, cleanup limits, implementation order, or native
  validation.
- Use `task-simplicity` for the final preflight check.
- Use `task-output` and `task-prohibitions` only when the user requests a formal implementation
  plan.

Do not load adjacent excerpts as background. Report the current task, inspected evidence, behavior
that must remain, smallest complete change, necessary validation, and any unresolved decision that
requires the user. Keep adjacent improvements outside the task.
