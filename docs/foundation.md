# Clean-slate foundation

## Boundary

qa-toolkit is a private, Linux x86_64 toolkit. It keeps every downloaded runtime and quality tool
under this repository's ignored `toolkit/` directory. An optional `~/.local/bin/qat` symlink may
point to the tracked launcher. Nothing else is installed globally.

Consumers opt in by tracking `.qat.toml`. Deployment consists of repository-local links and exact
ownership records. Evidence, work state, breaker state, and proof state live below `.git/qat/` in
the consumer. No state is shared between consumers.

## Retained intent

The foundation retains deterministic Python, Julia, source, documentation, vocabulary, security,
commit, hook, CI, evidence, and structured work-package checks. Shared defaults and the owned
vocabulary live here. Repository-specific settings remain in each consumer's tracked native files.

Gate commands are argument arrays executed sequentially with `shell=False`. `check` runs its plan
once. `sentinel` runs the check plan once. It next runs its additional plan once. Advisory findings do
not block, while invalid configuration, missing tools, and execution failures exit with status 2.

Git and Codex hooks use one dispatcher per event and repository-local `available/` and `enabled/`
links. Codex trust remains a manual `/hooks` decision. Structured JSON, not prose, is the authority
for active work packages and their Git and GitHub transitions.

## Explicit exclusions

This repository has no global plugin, target registry, provisioning receipt generations, Prek
lifecycle, global modes, session history, transcript handling, cross-repository breaker, or hidden
consumer dependency installation. It does not copy Unslopifier Git history.

## Delivery sequence

Implementation proceeds through registry, profiles, runner, corpus, Python, Julia, hooks, work
packages, CI, acceptance fixtures, and final documentation. Gridform is cut over only after the
toolkit foundation is merged and its exact revision is available for pinning.
