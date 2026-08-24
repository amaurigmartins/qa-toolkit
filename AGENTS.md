# qa-toolkit agent instructions

Keep this toolkit repository-scoped. Do not create global plugin state, a global target registry,
global session history, provisioning generations, or consumer QA dependencies.

Execute gate commands as argument arrays with `shell=False`. Dispatchers must pass arguments
unchanged, ignore non-regular entries, run enabled entries in lexical order, and never use `eval`.

Consumer native configuration is owned by the consumer. Sync must preserve it unless the user
explicitly selects `--hard-reset`. Unenrollment removes only paths recorded as toolkit-owned.

Codex hook trust is a manual `/hooks` decision. Never automate trust or permission escalation.

Work-package JSON is authoritative state. Markdown plans and task descriptions are inputs, never a
replacement for deterministic state transitions.

Use small utilities with one primary action. Avoid hidden recovery generations, global caches, and
framework layers that do not directly implement required behaviour.
