---
name: julia-convergence-review
description: Audit or plan post-refactor convergence of a Julia repository using live evidence, native language mechanisms, ownership, and dispatch doctrine. Use for explicit architecture reviews and cleanup plans, not routine implementation or ordinary code review.
---

# Julia Convergence Review

Treat inspection and planning as read-only unless the user separately authorizes implementation.
Reconstruct the live repository before judging it. Current requirements and supported numerical or
external behavior outrank old plans, examples, retained prompts, and remembered code.

The complete doctrine and cleanup prompt remain retained outside the ordinary context. Read only
exact excerpts through the supplied reader. Resolve this skill's directory, use it as the working
directory, and run:

```console
python scripts/read_convergence_sections.py --index references/sections.toml EXCERPT
```

Read each emitted excerpt completely. Start with `cleanup-reconstruct`. Select
`cleanup-architecture`, `cleanup-boundaries`, or `cleanup-planning` only when the live findings
require that analysis. Read `cleanup-output` only for a requested formal plan and
`cleanup-prohibitions` only before finalizing one. Do not open a complete source document unless
the user asks for an exhaustive reading.

Apply the Julia doctrines in strict order:

1. Use `native-admission` only for disputed semantic authorities. Use
   `native-mechanical-guardrails`, `native-repository-adoption`, or `native-acceptance` only for the
   corresponding audit stage.
2. Use `ownership-review` only when findings concern files, directories, modules, extensions,
   method placement, or dependency direction.
3. Use `dispatch-review` only when findings concern a public action with stable sequencing and
   dispatched stages. Do not apply Template Method to an abstraction rejected at the first step.

Every material finding must name current files or symbols, the observed responsibility, the defect
or justified warrant, behavior that must remain, the smallest corrective action, and repository-
native validation. Distinguish verified defects from mandatory-review candidates. Do not infer
defects from line count, method count, private naming, or doctrine vocabulary alone.

For a post-refactor plan, keep behavior-preserving convergence separate from intentional semantic
changes. For a review, lead with actionable findings ordered by impact. Do not edit code, create
work-package state, commit, publish, or change remote state unless the user explicitly requests
those actions.
