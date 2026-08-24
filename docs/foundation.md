# Repository-scoped foundation

## Boundary

qa-toolkit is a private Linux x86_64 toolkit. It keeps every downloaded runtime and quality tool
under this repository's ignored `toolkit/` directory. An optional `~/.local/bin/qat` symlink may
point to the tracked launcher. The bootstrap writes no other path outside this repository.

Consumers opt in by tracking `.qat.toml`. Deployment consists of repository-local links and exact
ownership records. Evidence, work state, breaker state, and proof state live below `.git/qat/` in
the consumer. Each consumer has independent state.

## Directory ownership

| Path | Owner and purpose |
| --- | --- |
| `registry/tools.json` | Tracked accepted versions, sources, assets, checksums, and executables. |
| `toolkit/` | Ignored active payload and temporary download data. |
| `profiles/*.toml` | Tracked complete tool, gate, hook, skill, severity, timeout, and order choices. |
| `config/<tool>/` | Tracked shared native tool configuration and locked central environments. |
| `corpus/vocabulary.toml` | Tracked shared terminology source. |
| `library/` | Tracked hooks, skills, prompts, templates, and work-package inputs. |
| `ci-workflows/` and `.github/workflows/` | Tracked reusable workflow source and repository CI. |
| Consumer `.qat.toml` | Tracked profile selection and repository-owned additions. |
| Consumer `.qat/` | Ignored deployed links and generated resolved configuration. |
| Consumer `.git/qat/` | Ignored ownership, merge bases, evidence, caches, work, and guardrail state. |
| Consumer `.agents/skills/` | Ignored links to the selected central skills. |
| Consumer `.codex/hooks*` | Ignored repository-local hook definition and dispatch entries. |

## Tool updates

`qat tool list` reads the tracked catalogue. `qat tool status` verifies each accepted version from the
active payload. `qat tool fetch TOOL` or `qat tool fetch --all` stages and verifies missing payloads.

`qat tool update TOOL VERSION URL SHA256 --archive FORMAT` updates one standalone tool. The command
downloads into `toolkit/.staging`, verifies the checksum and version output, then replaces the
active directory and catalogue entry together. A failed update restores the active directory and
leaves the tracked catalogue unchanged. Shared Python, Node, and Julia environments instead use
their tracked locks and bootstrap recipes. Change those inputs and rebuild the affected environment.

The toolkit keeps one active accepted installation. It has no global download cache and no stored
rollback generations.

## Profiles and native configuration

A profile is complete and cannot inherit another profile. It names every selected tool, managed
configuration, hook, skill, and ordered gate. The consumer file may add bounded native settings:

- A Python project path and stricter typed Ruff, Pylint, or Pydoclint settings.
- A tracked ast-grep configuration and rule-test directory.
- A tracked vocabulary file, additions, and path-bounded allowances.
- Tracked additive argument-array gates, including an opaque live-test command.
- Protected paths and structured work-package settings.

Unknown fields, unsafe paths, weaker Python settings, copied central rules, and raw invocations of
a centrally owned tool fail validation. Import Linter runs only when the selected Python project
contains tracked non-empty direction rules.

Enrollment prefers symlinks. A profile may declare a copied configuration only when a tool cannot
consume a link. Sync applies a three-way merge between the recorded base, the local copy, and the
new central input. On conflict, it leaves the local copy unchanged and records the three inputs in
`.git/qat`. `--hard-reset` is the sole discard operation.

## Retained intent

The foundation retains deterministic Python, Julia, source, documentation, vocabulary, security,
commit, hook, CI, evidence, and structured work-package checks. Shared defaults and the owned
vocabulary live here. Repository-specific settings remain in each consumer's tracked native files.

Gate commands are argument arrays executed sequentially with `shell=False`. `check` runs its plan
once. After the check plan completes once, `sentinel` runs its additional plan once. Advisory
findings do not block. Invalid configuration, missing tools, and execution failures exit with
status 2.

The runner selects gates from tracked-path triggers and an optional profile variant. It resolves
central Python settings, consumer ast-grep rules, conditional Import Linter settings, corpus input,
and consumer gates before execution. The evidence summary records the complete planned order,
argument arrays, severity, result classification, toolkit revision, target revision and dirty state,
profile digest, variant, and output-file names. Separate files retain complete standard output and
standard error.

`qat evidence show` prints the latest summary. `qat evidence export --destination PATH` copies one
complete run to a new path and refuses to replace an existing destination.

## Hooks and guardrails

Git and Codex hooks use one dispatcher per event and repository-local `available/` and `enabled/`
links. Enable and disable operations change only local links. They never change a central script's
executable bit. Dispatchers ignore irregular entries, run enabled regular scripts in lexical order,
pass arguments unchanged, and never call `eval`.

The six Codex events are `SessionStart`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `Stop`,
and `SessionEnd`. They retain protected-path decisions, permission checks, observed mutation checks,
an optional post-mutation fast check, and Stop proof. The current breaker and proof records live in
the target's `.git/qat/guardrails`. Codex trust remains a manual `/hooks` decision.

Enrollment refuses foreign Git hooks unless the caller explicitly selects `--adopt-hooks`.
Unenrollment restores adopted hooks from the recorded local backup. A changed owned hook causes
unenrollment to stop unless the caller supplies a backup path or explicitly selects `--hard-reset`.

## Structured work packages

Markdown plans and task files are immutable human inputs. JSON below `.git/qat/work` is the active
state. The small `qat work` commands retain repository, branch, base revision, expected parent,
issue and pull-request numbers, one active task, allowed paths, validation argument arrays,
provisional and final commits, exact-lease publication, results, and evidence references.

`init`, `stage`, `bind`, `reconcile`, `finish`, and `retire` each perform one checked transition.
Interrupted publication can be reconciled only when local and remote Git identities match a known
state. Repository-local skills call these utilities. Prose cannot advance the JSON state. GitHub
issue, pull-request, check, comment, and ready operations use the bundled GitHub CLI through bounded
arguments and verify the returned repository identity.

## CI

`.github/workflows/reusable-sentinel.yml` accepts an exact 40-character toolkit revision. It checks
out the consumer and that exact toolkit commit separately, reconstructs `toolkit/`, enrols the
consumer, validates commits, runs Sentinel once, and uploads the consumer's complete evidence
directory. Callers must pin the workflow or checkout to an immutable toolkit commit.

Private reusable-workflow access is a repository setting, not a toolkit side effect. When selective
access is unavailable, a private consumer can checkout this repository at the exact commit inside
its own workflow and run the same tracked commands.

## Explicit exclusions

This repository has no global plugin, target list, provisioning receipt generations, Prek install
state, global modes, session history, transcript handling, cross-repository breaker, or hidden
consumer dependency installation. It does not copy another repository's Git history.

Users can disable these repository guardrails. They do not provide host containment. CI remains
authoritative for merge acceptance. The toolkit supports only Linux x86_64. The project makes no
public stability or third-party support promise.

## Foundation audit

The final foundation diff was checked for these failure modes:

- Payload, cache, evidence, work, or guardrail state outside `toolkit/` and the target's `.git/qat`.
- Global plugin files, target lists, session records, transcripts, and breaker state.
- Writes to consumer dependency declarations or locks.
- Shell-string gate execution, `shell=True`, and `eval`.
- Duplicate gate identifiers and repeated check gates inside Sentinel.
- Unmanaged hook replacement and unenrollment outside recorded ownership.
- Cross-repository state when two consumers run concurrently.

The only implicit optional global write is the documented `--link-launcher` symlink. Backup,
evidence export, and report commands write elsewhere only when the user names a destination.
Consumer Python and Julia dependency files are product inputs. The toolkit uses central QA
environments and disposable Julia copies. The acceptance fixtures verify independent enrollment,
hooks, breaker state, evidence, and work state for two repositories.

The foundation proof passed 234 tests with one explicit Julia acceptance skip and 95.62% branch
coverage. Both Julia runtimes, every selected fast gate, repository isolation, exact cleanup,
advisory classification, and work-package recovery passed.

Gridform must not pin a foundation branch. Its cutover begins only after this repository merges and
provides the exact merged revision.
