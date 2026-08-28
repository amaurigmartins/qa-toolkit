---
name: julia-structural-design
description: Design or implement Julia structural changes involving abstractions, dispatch interfaces, modules, source layout, wrappers, or compatibility paths. Do not use for ordinary method-body fixes, numerical edits within an established owner, formatting, or docstrings.
---

# Julia Structural Design

Use the current task, repository instructions, live code, supported behavior, and tests as the
evidence base. Examples in the doctrine files illustrate decisions. They do not name required
repository objects or authorize unrelated refactors.

Apply the doctrines in this order:

1. Native-first admission decides whether a project-owned abstraction should exist.
2. Ownership and responsibility decide where an admitted concept belongs.
3. Dispatch-driven Template Method applies only to an admitted first-class action with stable
   sequencing and genuine type-dependent variation.

The complete doctrine files remain retained outside the ordinary context. Read only exact excerpts
through the supplied reader. Resolve this skill's directory, use it as the working directory, and
run:

```console
python scripts/read_structural_sections.py --index references/sections.toml EXCERPT
```

Read each emitted excerpt completely. Do not open a complete doctrine file unless the user asks
for an exhaustive reading. Select excerpts narrowly:

- Use `native-admission` before adding a generic function, type, trait, or other semantic
  authority.
- Use `native-helpers` for helpers and Julia-native replacement mechanisms.
- Use `native-compatibility` for wrappers, contexts, registries, adapters, shims, or compatibility
  paths.
- Use `ownership-laws`, then only the relevant `ownership-*` placement or growth excerpt, when
  changing files, directories, modules, extensions, or method placement.
- Use `dispatch-laws` and the relevant `dispatch-*` excerpt only after admitting a public action
  with fixed sequencing and genuine dispatched variation.
- Use mechanical, adoption, acceptance, or review excerpts only for explicit cleanup or audit
  work.

Do not read adjacent excerpts merely for background.

Prefer Core, Base, standard-library, dependency-owned, and already admitted repository interfaces.
Prefer another method on an existing generic over a new generic name. Keep direct owner-local code
when no stable reusable semantics exist. Preserve numerical results, units, ordering, supported
interfaces, and repository-native validation unless the user explicitly requests a behavior
change.

Do not manufacture compatibility for unreleased or unsupported shapes. Do not preserve old and new
execution paths in parallel after a coherent replacement. Do not introduce architecture merely to
make the repository resemble an example in a doctrine file.
