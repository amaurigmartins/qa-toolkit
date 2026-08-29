# qa-toolkit

Repository-scoped quality tooling for Python, Julia, documentation, Git, GitHub, and Codex.

qa-toolkit keeps a pinned tool bundle in this checkout and applies a selected, complete quality
profile to another Git repository. A consumer opts in with one tracked `.qat.toml` file. Enrollment
then creates only local links and state in that consumer.

This is the practical guide. For the ownership rules and design record, see
[docs/foundation.md](docs/foundation.md).

## What you get

- Fast and full quality plans with stable gate order, timeouts, severities, and exit codes.
- Python formatting, linting, typing, docstring, dead-code, structure, import-direction, test, and
  dependency checks.
- Julia formatting, source, test, Aqua, explicit-import, and vulnerability checks with exact Julia
  runtimes.
- Spelling, technical-prose, terminology, acronym, and optional semantic identifier checks.
- Secret, shell, and GitHub Actions checks in profiles that select them.
- Conventional Commit validation against a shared and repository-specific vocabulary.
- Optional Git and Codex hooks that can be enabled or disabled per repository.
- Complete local evidence for every quality run.
- Deterministic work-package commands for staged commits, validation, and exact-lease publication.
- An optional containerized Mermaid-to-PDF renderer.

The selected profile decides which of these are active. Installing qa-toolkit does not make every
gate run in every consumer.

## The short version

For a fresh clone of this repository:

```console
./bootstrap.sh
bin/qat profile validate qa-toolkit
bin/qat repo enroll .
bin/qat check --target .
bin/qat sentinel --target .
```

If this checkout is already enrolled, use `bin/qat repo status .`. Run `bin/qat repo sync .` when
the profile, `.qat.toml`, toolkit revision, deployed hooks, or deployed links have changed.

For another repository:

1. Bootstrap this central checkout once.
2. Add and commit a `.qat.toml` in the consumer repository.
3. Prepare the consumer's own dependencies, such as its Python virtual environment or Julia project.
4. Enroll the consumer with this checkout's launcher.
5. Run `check` while developing and `sentinel` before publishing.

```console
/path/to/qa-toolkit/bootstrap.sh
/path/to/qa-toolkit/bin/qat repo enroll /path/to/consumer
/path/to/qa-toolkit/bin/qat check --target /path/to/consumer
/path/to/qa-toolkit/bin/qat sentinel --target /path/to/consumer
```

All later examples use `qat`. Either replace it with `/path/to/qa-toolkit/bin/qat`, or run
`./bootstrap.sh --link-launcher` and put `~/.local/bin` on `PATH`.

## Requirements and installation

The bootstrap supports Linux x86_64 only. It requires:

- POSIX `sh`;
- Git and `tar`;
- `curl` or `wget`;
- `sha256sum` or `shasum`;
- network access to retrieve the pinned payloads.

Run:

```console
./bootstrap.sh
bin/qat tool status
```

Bootstrap installs the accepted Python runtime, Python packages, Node packages, Julia runtimes,
and standalone tools below the ignored `toolkit/` directory. It fetches the complete central
catalog, not only the tools used by one profile. Re-running it rebuilds the pinned Python
environment and ensures that the rest of the catalog matches the tracked locks and checksums.

The optional launcher link is the only bootstrap write outside this checkout:

```console
./bootstrap.sh --link-launcher
qat --help
```

It creates `~/.local/bin/qat` only when that path is absent or already points to this checkout. It
will not replace a foreign path.

Bootstrap does not install a consumer's application dependencies or modify its dependency files.
A Python consumer that imports third-party packages should prepare its virtual environment. A Julia
consumer remains responsible for its tracked `Project.toml`, test dependencies, test selectors,
and portable continuous integration setup.

## How the pieces fit together

There are three distinct layers:

| Layer | Owner | Purpose |
| --- | --- | --- |
| Central checkout | qa-toolkit | Pinned payloads, profiles, shared rules, hooks, skills, and the `qat` launcher. |
| Tracked consumer files | Consumer | `.qat.toml`, native project configuration, vocabulary, custom rules, and custom gate scripts. |
| Local consumer state | qa-toolkit deployment | Links in `.qat/`, evidence and state in `.git/qat/`, and optional hook or skill links. |

Enrollment records the exact toolkit revision, profile digest, consumer digest, owned paths,
hooks, skills, and executable links. Quality commands refuse to run when this record is stale.
Run `qat repo sync TARGET` after changing any declared input or after updating qa-toolkit.

Enrollment adds its own generated paths to the consumer's `.git/info/exclude`. It does not edit
the consumer's tracked `.gitignore`.

## Profiles and available checks

A profile is a complete selection. Profiles do not inherit from each other, and a consumer cannot
remove a central gate from its selected profile.

| Profile | `check` gates | Additional `sentinel` gates | Hooks |
| --- | --- | --- | --- |
| `disposable-documentation` | Spelling, technical prose | None | None |
| `disposable-python` | Python format, Ruff, MyPy, Pylint, Pydoclint, Vulture, Grain, structural lint, universal and Python ast-grep, spelling, prose | Test suite with 95% coverage | None |
| `disposable-julia` | Julia source, version-selected formatting, spelling, prose | Version-selected tests, Aqua, explicit imports, and Julia manifest vulnerabilities | None |
| `disposable-hooks` | None | None | Git, Codex, and work-package skills |
| `gridform` | Secrets, shell, workflow syntax and security, most Python checks, ast-grep, spelling, prose | Python structural lint, dependency audit, and non-destructive tests with 95% coverage | Git, Codex, and work-package skills |
| `linecablemodels` | Secrets, workflow syntax and security, Julia source and format, spelling, prose | Default and `tag:quality` Julia tests on 1.12.6 | Git, Codex, Julia, and work-package skills |
| `qa-toolkit` | This repository's Python, ast-grep, spelling, and prose checks | Test suite with 95% coverage | Git, Codex, and work-package skills |

Every documentation-capable profile also defines `text-ai-tells` as an advisory gate. It runs only
with `qat advisory` or the `--advisory` option.

The `gridform`, `linecablemodels`, and `qa-toolkit` profiles encode repository-specific commands.
Use a `disposable-*` profile as the general starting point unless the consumer is the named
repository.

`disposable-julia` requires an explicit runtime variant for its version-specific gates:

```console
qat check --target /path/to/consumer --variant 1.10.11
qat sentinel --target /path/to/consumer --variant 1.12.6
```

The supported variants are `1.10.11` and `1.12.6`. Without a variant, the profile still runs its
unversioned source and text gates, but skips formatting, tests, Aqua, explicit imports, and the
manifest vulnerability gate.

Inspect the exact profile rather than guessing:

```console
qat profile validate disposable-python
sed -n '1,240p' /path/to/qa-toolkit/profiles/disposable-python.toml
```

`profile validate` prints the selected tools, configurations, gate IDs, hooks, skills, and profile
digest. A tool can be exposed in `.qat/bin` without being scheduled as a gate. The profile's
`[[gates]]` entries are the authoritative run plan.

### What the main gates do

| Gate or group | Behavior |
| --- | --- |
| `repository-secrets` | Runs Gitleaks against the repository with redacted output. |
| `shell-syntax` | Runs ShellCheck against tracked regular `.sh` files. |
| `workflow-syntax` | Runs actionlint against GitHub Actions workflows. |
| `workflow-security` | Runs the selected workflow security scanner offline and in pedantic mode. |
| `python-format` | Checks formatting with the central Ruff configuration. It does not rewrite files. |
| `python-lint` | Runs the selected central Ruff rules plus permitted stricter consumer settings. |
| `python-types` | Runs strict MyPy with generated repository-local configuration. |
| `python-pylint` | Runs Pylint with the central configuration and optional stricter settings. |
| `python-docstrings` | Checks Python docstrings with Pydoclint. |
| `python-dead-code` | Reports dead code with Vulture. |
| `python-grain` | Runs the central Grain source and documentation rules. |
| `python-structure` | Runs structural Python rules with Slop. Its phase differs by profile. |
| `python-import-directions` | Appears automatically when the tracked Python `pyproject.toml` contains non-empty Import Linter direction rules. |
| `python-dependencies` | Audits the configured consumer environment with pip-audit. It is currently specific to the `gridform` layout. |
| `python-tests` | Runs the profile's test command and coverage threshold. |
| `ast-grep-*` | Runs central universal or language-specific structural rules. |
| `julia-source` | Checks tracked Julia source structure. |
| `julia-format*` | Checks JuliaFormatter output on a private tracked-source copy. |
| `julia-tests*` | Instantiates and tests each eligible root or nested package in a private copy. |
| `julia-aqua*` | Runs Aqua for each eligible package in a private copy. |
| `julia-explicit-imports*` | Checks explicit imports for each eligible package. |
| `julia-vulnerabilities` | Scans tracked Julia manifests with Trivy. |
| `text-spelling` | Runs CSpell on tracked reader text using the resolved vocabulary. |
| `text-prose` | Runs blocking Vale rules on tracked Markdown, LaTeX, and package docstrings. |
| `text-ai-tells` | Reports advisory prose candidates; findings do not block. |

Julia tools copy tracked regular files to a temporary directory before formatting, instantiation,
or testing. An absent package manifest may be resolved only in that copy. The consumer's tracked
source and dependency files are not rewritten.

## Configure a consumer

The consumer must be an ordinary Git worktree with a `.git` directory and at least one commit.
The `.qat.toml` file and every declared path must exist and be tracked before enrollment.

This is a minimal documentation consumer:

```toml
schema_version = 1
profile = "disposable-documentation"
native_configurations = []
protected_paths = []

[vocabulary]
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
```

Create and enroll it:

```console
git add .qat.toml
git commit -m "chore(quality): configure qa toolkit"
qat profile validate disposable-documentation
qat repo enroll .
qat repo status .
qat check --target .
```

`profile validate` validates the central profile. `repo enroll` is the operation that validates
the consumer declaration, its tracked paths, available payloads, hooks, and executable links.

### A Python consumer example

```toml
schema_version = 1
profile = "disposable-python"
native_configurations = ["pyproject.toml"]
protected_paths = ["src", "tests"]

[vocabulary]
file = ".qat-vocabulary.toml"
additions = ["MyProject"]
allowances = []

[python]
project = "."

[python.ruff]
paths = ["src", "tests"]
known_first_party = ["my_project"]
extend_select = ["C90"]
enforce = []

[python.ruff.thresholds]
max_complexity = 8

[python.pylint]
paths = ["src"]
enable = []

[python.pydoclint]
paths = ["src"]

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true

[text.prose]
include = ["README.md", "docs/**", "src/**/*.py"]
exclude = ["docs/quoted-sources/**"]
```

Add a lock file to `native_configurations` when the repository tracks one and wants changes to it
to invalidate the deployed consumer identity.

Python defaults assume a `src/` package and `tests/` below `python.project`. For a flat layout,
declare explicit paths. Ruff paths also select MyPy inputs. Pylint paths also select Vulture and
the default coverage package. Pydoclint paths are independent. These paths are repository-relative
literals, not glob patterns, and each configured path must contain tracked input.

qa-toolkit uses the first executable Python found at these locations, in order:

1. The project virtual environment.
2. The repository-root virtual environment.
3. the central qa-toolkit Python.

The generated Python environment adds the project, its `src/`, and existing consumer site-packages
to the Python import path. qa-toolkit still does not create the consumer's virtual environment or
install the consumer's dependencies.

### A Julia consumer example

```toml
schema_version = 1
profile = "disposable-julia"
native_configurations = ["Project.toml", "Manifest.toml", "test/runtests.jl"]
protected_paths = ["src", "test"]

[vocabulary]
additions = ["MyJuliaPackage"]
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
```

Then select the runtime on every quality command:

```console
qat check --target . --variant 1.12.6
qat sentinel --target . --variant 1.12.6
```

Do not list `Manifest.toml` when the repository intentionally does not track one. Julia package
tests remain repository-owned. qa-toolkit calls the tracked package test entry point.

## `.qat.toml` reference

The schema is closed. Unknown fields fail rather than being ignored.

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | Yes | Must be `1`. |
| `profile` | Yes | Exact profile filename without `.toml`. |
| `native_configurations` | No | Existing tracked consumer-owned inputs included in the consumer identity. Sync never rewrites them. |
| `protected_paths` | No | Extra paths protected by Codex guardrails. This does not exclude or select quality inputs. |
| `[vocabulary]` | No | Optional vocabulary file and short accepted-word arrays. |
| `[ast_grep]` | No | Optional tracked ast-grep configuration and required rule-test directory. |
| `[python]` | No | Project location and typed additions to central Python settings. |
| `[text.prose]` | No | Include and exclude patterns for Vale only. |
| `[[gates]]` | No | Additive consumer-owned gate commands. |
| `[work]` | Yes | Repository-local work state directory and allowed-path requirement. |

`work.state_directory` must be below `.git/qat`, and the standard value is
`.git/qat/work`. `work.require_allowed_paths` must be a Boolean. Work initialization currently
requires at least one explicit allowed path regardless of that Boolean.

### Python settings

Consumer Python settings can add rules or make selected central settings stricter. They are not a
replacement native tool configuration.

| Table | Accepted fields |
| --- | --- |
| `[python]` | `project` |
| `[python.ruff]` | `extend_select`, `enforce`, `paths`, `known_first_party` |
| `[python.ruff.thresholds]` | `max_complexity`, `max_args`, `max_returns` |
| MyPy child table | Plugins, import search paths, explicit package bases, and namespace packages |
| `[python.pylint]` | `enable`, `paths`, `min_similarity_lines` |
| `[python.pydoclint]` | `paths`, `skip_checking_short_docstrings`, `check_class_attributes` |
| `[[python.exceptions]]` | `tool`, `rule`, `path`, `reason` |

`ruff.enforce` can enable only rules that the central configuration explicitly ignores.
Thresholds cannot be weaker than central values. MyPy Boolean additions can only be `true`.
Pydoclint can only tighten short-docstring and class-attribute checks.

## Exclusions, allowances, and custom rules

There is no single repository-wide `exclude` field. Each setting has a narrow purpose so that an
exception for prose cannot silently disable tests, security checks, or source analysis.

### Exclude paths from prose analysis

Use `[text.prose]` for Vale:

```toml
[text.prose]
include = ["docs/**", "papers/**/*.tex", "src/**/*.py"]
exclude = ["docs/generated/**", "papers/quoted-sources/**"]
```

When `include` is absent, Vale considers all supported tracked reader text. When it is present,
only matching paths are considered. `exclude` is applied after that selection. Patterns must be
bounded, repository-relative POSIX patterns: no absolute path, `..`, or backslash.

This setting affects both blocking `text-prose` and advisory `text-ai-tells`. It does not affect
`text-spelling`, Python analyzers, Julia gates, ast-grep, tests, or custom gates.

The text tools read tracked regular Markdown, LaTeX, Python, and Julia files, plus recognized
license filenames. Python and Julia analysis uses reader-facing docstrings, and Markdown or LaTeX
is mapped to a reader view. Inline Vale disable directives are rejected.

### Accept project words or allow a term on specific paths

For a few repository-wide accepted words, use the short form:

```toml
[vocabulary]
additions = ["Gridform", "LineCableModels"]
allowances = ["RLS"]
```

At present, both arrays contribute repository-wide accepted words. Neither is a path exclusion,
and neither can turn off a shared central error rule.

For replacements, acronyms, locale, source classification, or reason-bearing path allowances,
track a schema-1 vocabulary file:

```toml
# .qat-vocabulary.toml
schema_version = 1

[settings]
locale = "en-GB"

[terminology]
accepted = ["Gridform"]
rejected = ["utilize"]

[terminology.replacements]
utilize = "use"

[acronyms]
accepted = ["RLS"]

[[allowances]]
term = "robust"
paths = ["docs/quoted-source.md"]
reason = "The document quotes an external title."

[sources]
generated_patterns = ["docs/generated/**"]
```

Reference it from `.qat.toml`:

```toml
[vocabulary]
file = ".qat-vocabulary.toml"
additions = []
allowances = []
```

The file must be tracked. The only locales are the central `en-US` default and explicit `en-GB`.
A path allowance suppresses the named literal term only on matching paths. A
`sources.generated_patterns` entry classifies matching tracked text as generated, so both prose
and spelling readers skip it and report the source decision on standard error. Use that mechanism
only for genuinely generated inputs.

Schema 3 is the specialized alternative. It adds Python identifier terminology, replacements,
semantic roles, callable grammars, path-specific ownership boundaries, visibility selection, and
required accepted and rejected cases. Declaring a schema-3 file adds the
`python-semantic-vocabulary` check gate. See the complete working example in
[`tests/test_vocabulary.py`](tests/test_vocabulary.py).

### Add a reason-bearing Ruff exception

Only Ruff supports a consumer rule exception:

```toml
[[python.exceptions]]
tool = "ruff"
rule = "S603"
path = "tests/**"
reason = "Tests execute fixed argument arrays."
```

The rule must be active after settings are resolved, the glob must match a tracked regular file,
and the reason must be non-empty. This creates a generated per-file ignore. MyPy, Pylint,
Pydoclint, Vulture, and the other central gates do not accept generic rule suppressions through
`.qat.toml`.

### Narrow Python roots

Use the typed `paths` fields when only part of a repository is a Python project:

```toml
[python]
project = "services/api"

[python.ruff]
paths = ["services/api/src", "services/api/tests"]

[python.pylint]
paths = ["services/api/src"]

[python.pydoclint]
paths = ["services/api/src"]
```

These fields accept literal repository paths, not globs. They select analysis roots. They are not
rule-specific exclusions.

### Add tested ast-grep rules

Declare both a tracked ast-grep config and a tracked test directory:

```toml
[ast_grep]
config = "quality/ast-grep.yml"
tests = "quality/rule-tests"
```

The config must contain a non-empty `ruleDirs` list. Every selected consumer rule needs a unique
ID and a test file with at least one `valid` and one `invalid` case. Consumer rules cannot copy a
central rule ID or body. qa-toolkit adds `consumer-ast-grep-tests` and
`consumer-ast-grep-scan` to the check plan.

### Add a custom gate

Consumer gates are additive argument arrays:

```toml
[[gates]]
id = "package-smoke"
phase = "sentinel"
argv = ["./scripts/smoke-test", "--offline"]
triggers = ["src/**", "tests/**", "scripts/smoke-test"]
timeout = 300
severity = "blocking"
variants = ["full"]
finding_exit_codes = [1]
execution_error_exit_codes = [2]
before = "python-tests"
```

| Field | Meaning |
| --- | --- |
| `id` | Unique gate ID across the resolved central and consumer plan. |
| `phase` | `check` or `sentinel`. Sentinel runs both phases. |
| `argv` | Non-empty argument array executed directly with no shell. |
| `triggers` | Gate-selection patterns used only when `--changed` is supplied. |
| `timeout` | Positive timeout in seconds. |
| `severity` | `blocking` or `advisory`. |
| `variants` | Empty for every variant, or the accepted `--variant` values. |
| `finding_exit_codes` | Positive exit codes classified as findings. |
| `execution_error_exit_codes` | Documented error exits. Every other nonzero exit is also treated as an execution error. |
| `before` | Optional existing gate ID that this consumer gate must precede. |

A relative executable containing a slash, such as `./scripts/smoke-test`, must be tracked. The
runner passes the variant in `QAT_VARIANT`. A consumer gate cannot invoke a centrally owned tool
already selected by the profile. Configure that tool through its typed settings instead.

## Run quality gates

### `qat check`

Runs every selected blocking check-phase gate once:

```console
qat check --target /path/to/consumer
qat check --target . --advisory
qat check --target . --changed src/api.py --changed tests/test_api.py
```

`--advisory` includes advisory check-phase gates in the same run. `--changed` can be repeated. It
selects gates whose trigger patterns match at least one named path. It does not restrict what a
selected tool scans. With no `--changed`, all gates eligible for the phase and variant run.

### `qat sentinel`

Runs the check plan once. It next runs every selected sentinel-phase gate once:

```console
qat sentinel --target /path/to/consumer
qat sentinel --target . --variant full --advisory
```

On a successful stable run, Sentinel records a proof bound to the toolkit revision, target
revision, worktree state, profile, consumer configuration, and evidence. Codex Stop guardrails can
require this current proof.

### `qat advisory`

Runs only advisory check-phase gates:

```console
qat advisory --target /path/to/consumer
```

Advisory findings are printed and retained but do not produce exit status `1`. An invalid
configuration, unavailable tool, timeout, or other execution error still exits `2`.

### Results and exit status

The runner prints one line per gate and always prints the evidence directory:

```text
[PASS] python-format
[FINDING] text-prose
evidence: /path/to/consumer/.git/qat/evidence/20260829T120000Z-0123456789ab
```

| Exit | Meaning |
| --- | --- |
| `0` | No blocking finding and no execution error. Advisory findings may exist. |
| `1` | At least one blocking gate reported a finding. |
| `2` | Planning, configuration, spawning, timeout, or gate execution failed. |

A normal finding does not stop later gates. An execution error stops later gates, which are
recorded as `not-run`.

## Command reference

### Repository lifecycle

| Command | What it does |
| --- | --- |
| `qat profile validate PROFILE` | Validates one central profile and prints its exact selection and digest. It does not validate a consumer. |
| `qat repo enroll TARGET [--adopt-hooks]` | Validates tracked consumer inputs, creates local state and links, and installs selected hooks and skills. Refuses an already enrolled target. |
| `qat repo status TARGET` | Compares the deployment with current toolkit, profile, consumer inputs, links, hooks, and skills. Exits `1` when stale. |
| `qat repo sync TARGET [--adopt-hooks] [--hard-reset]` | Reconciles an existing deployment after declared inputs or the toolkit change. Preserves consumer native configuration. |
| `qat repo unenroll TARGET [--backup PATH] [--hard-reset]` | Removes only recorded toolkit-owned paths and local-exclude lines, then removes `.git/qat` state. |

Enrollment refuses an existing Git hook, Codex hook, or Codex definition unless `--adopt-hooks`
is explicit. Adoption snapshots the foreign path below `.git/qat` and restores it during
unenrollment.

Sync preserves local enable or disable state for hooks. Managed copied configurations use a
three-way merge against their recorded base. A conflict leaves the target unchanged and writes the
inputs below `.git/qat/conflicts`. `--hard-reset` is the only sync option that can discard a changed
managed path, hook, skill, or executable link. It never rewrites a path listed in
`native_configurations`.

Unenrollment stops when an owned path was modified. `--backup PATH` preserves modified managed
paths outside the target before removal. `--hard-reset` discards those modifications. The parsed
`--purge-config` option is intentionally unsupported and exits `2`. `.qat.toml` and all other
consumer-owned tracked configuration remain. Remove them manually in a separate commit if that is
the desired repository change.

### Hooks

| Command | What it does |
| --- | --- |
| `qat hook status TARGET` | Prints installed dispatcher, entry, Codex breaker, and Sentinel proof state. Exits `1` when hook deployment is stale. |
| `qat hook enable TARGET [--kind KIND] [--event EVENT] [--entry NAME]` | Enables every selected entry matching all supplied filters. With no filters, enables all selected entries. |
| `qat hook disable TARGET [--kind KIND] [--event EVENT] [--entry NAME]` | Disables every selected entry matching all supplied filters. With no filters, disables all selected entries. |
| `qat hook dispatch ...` | Internal dispatcher used by installed Git and Codex hook paths. Do not call it directly. |

Examples:

```console
qat hook status .
qat hook disable . --kind git --event pre-commit --entry quality
qat hook enable . --kind codex --event PostToolUse --entry fast-check
```

Profiles with hooks enable the Git `pre-commit` quality check, the Git `commit-msg` check, and the
main Codex guardrails by default. The Codex post-mutation `fast-check` entry is available but
disabled by default.

Codex hook trust is always a manual `/hooks` decision. Enrollment writes the exact local
`.codex/hooks.json`, but qa-toolkit never grants trust or escalates permissions. `protected_paths`
adds to the automatically protected `.qat.toml`, `.qat/**`, `.git/**`, `.codex/hooks*`, and
`.agents/skills/**` paths. These guardrails are repository checks, not host containment, and users
can disable them.

### Commit messages

Choose exactly one input:

```console
qat commits --target . --commit HEAD
qat commits --target . --range origin/main..HEAD
qat commits --target . --message-file .git/message.txt
```

The message-file form accepts only a regular file below the target `.git` directory. The command
checks Conventional Commit syntax, supported types, a non-empty scope, a lowercase imperative
subject of at most 72 characters, and shared or consumer terminology. Merge, revert, fixup, amend,
and squash lifecycle messages are skipped where appropriate.

### Tool bundle

| Command | What it does |
| --- | --- |
| `qat tool list [--json]` | Lists every accepted catalog entry, version, and environment. |
| `qat tool status [TOOL ...] [--json]` | Verifies all tools or the named tools against accepted version output. Exits `1` when any selection is not current. |
| `qat tool fetch TOOL... [--force]` | Fetches named tools or environments. |
| `qat tool fetch --all [--force]` | Fetches the complete catalog. Tool IDs and `--all` are mutually exclusive. |
| `qat tool update TOOL VERSION URL SHA256 --archive FORMAT [--version-contains TEXT]` | Maintainer command that atomically updates one standalone payload and its tracked catalog entry. |

Archive formats are `raw`, `tar.gz`, `tar.xz`, and `zip`. Shared Python, Node, and Julia
environments cannot be updated with `tool update`. Change their tracked locks or bootstrap recipes
and rebuild instead. qa-toolkit keeps one active accepted installation and no rollback generation.

### Corpus and evidence

```console
qat corpus build --target .
qat evidence show --target .
qat evidence show --target . --run .git/qat/evidence/RUN_ID
qat evidence export --target . --run .git/qat/evidence/RUN_ID --destination /tmp/qat-run
```

`corpus build` validates and generates the resolved CSpell, Vale, terminology, source-decision,
and other text inputs below `.qat/generated/corpus`.

`evidence show` prints `summary.json` for the latest run unless `--run` selects another direct
child of the repository-local evidence directory. `evidence export` copies the complete selected
run, including standard output and standard error files. It refuses an existing destination.

### Mermaid PDFs

```console
qat docs mermaid --source diagrams
qat docs mermaid --source diagrams --target rendered --engine podman
qat docs mermaid --source diagrams --force --timeout 600
```

The command renders every regular `.mmd` below the source, preserves relative paths, and writes
PDFs to `SOURCE/mermaid-pdf` by default. Content stamps skip outputs whose source and pinned
renderer identity have not changed. `--force` renders all inputs again. Auto selection prefers
Podman before Docker.

The renderer uses Mermaid CLI 11.16.1 in an image pinned by digest, disables container networking,
and mounts the source read-only. The selected container engine may fetch the image on first use.
This utility is independent of profiles, bootstrap selection, enrollment, `check`, and `sentinel`.

### Work packages

Work packages are a specialized publication workflow. Markdown plans are retained inputs. JSON
below the configured `.git/qat/work/WORK_ID` directory is the authoritative state.

The normal sequence is:

```text
init -> stage -> bind -> finish
                  \-> reconcile after an interrupted publication
```

| Command | What it does and changes |
| --- | --- |
| `qat work template NAME` | Prints one of `plan`, `breakdown`, `reconcile`, `cleanup`, or `release`. Read-only. |
| `qat work init WORK_ID ...` | Creates or advances local package state from explicit identity fields and Markdown inputs. Requires an exact clean parent; does not create a branch, commit, PR, or push. |
| `qat work stage WORK_ID` | Creates an empty provisional commit, creates or selects the declared branch, and pushes that exact commit. |
| `qat work bind WORK_ID --pull-request N` | Binds the staged local state to the exact draft pull-request number. |
| `qat work status WORK_ID` | Reports structured state plus exact local and remote branch identity. It contacts the declared remote. |
| `qat work finish WORK_ID` | Checks changed paths, runs stored validation argument arrays, stages all allowed changes, amends the provisional commit, and publishes with an exact force-with-lease. |
| `qat work reconcile WORK_ID [--pull-request N]` | Recovers only recognized staged or publishing states and may retry their exact push. It rejects divergent identities. |
| `qat work report WORK_ID [--output PATH]` | Renders a factual Markdown report from state and retained results. |
| `qat work retire WORK_ID` | Deletes only a completed cleanup package that requested retirement and has Sentinel proof. It does not delete Git history or remote records. |
| `qat work release --base-version VERSION --message MESSAGE...` | Calculates a SemVer bump from accepted commit messages. It does not edit files, tag, release, or publish. |

`work init` has a deliberately explicit interface. Run `qat work init --help` for all required
fields. Repeat `--allow-path` for literal files or directories and `--validation-json` for each
direct argument array:

```console
qat work init issue-42 \
  --repository owner/project \
  --issue 42 \
  --kind feature \
  --branch feature/42 \
  --base-branch main \
  --base-sha 0123456789abcdef0123456789abcdef01234567 \
  --plan-revision 1 \
  --task C01 \
  --title "Add parser validation" \
  --expected-parent 0123456789abcdef0123456789abcdef01234567 \
  --subject "feat(parser): validate bounded input" \
  --allow-path src/parser.py \
  --allow-path tests/ \
  --validation-json '["qat","check","--target","."]' \
  --proof check \
  --plan-file PLAN.md \
  --task-file TASK.md
```

Allowed paths are literal and cannot name toolkit-owned or `.git` paths. Validation is executed as
argument arrays with no shell. A `check` or `sentinel` validation matching `--proof` is mandatory.
`stage`, `finish`, and `reconcile` can mutate the local branch and remote. Use them only when that
publication is intended.

### Agent helpers

Generate a deterministic thread name without remote access:

```console
qat agent thread-name \
  --repository owner/project --issue 42 --task C01 --title "Add parser validation"
```

The task ID must have the form `C01`, and the output is repository-qualified JSON.

`qat agent github` wraps the bundled GitHub CLI with bounded operations:

| Operation | Required operation-specific options |
| --- | --- |
| `repository` | None |
| `issue-view` | `--number` |
| `issue-create` | `--title --body-file` |
| `issue-update` | `--number --title --body-file` |
| `pr-view` | `--number` |
| `pr-create` | `--head --base --title --body-file` |
| `pr-update` | `--number --title --body-file` |
| `pr-checks` | `--number` |
| `pr-comment` | `--number --body-file` |
| `pr-ready` | `--number` |

Every operation also requires `--repository OWNER/NAME`. View, checks, and repository operations
are read-only. Create, update, comment, and ready operations change GitHub state. The selected
profile must expose `gh`, the bundled CLI must be authenticated, and the returned repository
identity must match the request.

## Continuous integration

The reusable workflow retrieves the consumer and the exact qa-toolkit revision separately,
bootstraps, enrolls, optionally prepares the consumer runtime, optionally validates commits, runs
Sentinel once, and uploads complete evidence.

Use an exact 40-character qa-toolkit commit in both places:

```yaml
jobs:
  quality:
    uses: OWNER/qa-toolkit/.github/workflows/reusable-sentinel.yml@0123456789abcdef0123456789abcdef01234567
    with:
      toolkit_revision: 0123456789abcdef0123456789abcdef01234567
      base_sha: ${{ github.event.pull_request.base.sha }}
      setup_path: scripts/prepare-qa
      retention_days: 14
```

`setup_path` is optional. It must be a tracked executable relative path and receives no
interpolated arguments. Use it to create the consumer's virtual environment or perform other
repository-owned runtime setup. `variant` selects a profile variant. `base_sha` enables commit
validation for `BASE_SHA..HEAD`.

For a private consumer using a private qa-toolkit repository, use the exact-revision composite
action in `.github/actions/sentinel/action.yml`. GitHub's private-action delivery must be enabled
for the consumer. Private reusable-workflow access alone does not grant the consumer token
permission to clone another private repository. See [docs/foundation.md](docs/foundation.md) for
the credential and checkout boundary.

## What qa-toolkit intentionally does not do

- It does not support macOS, Windows, ARM, bare repositories, or linked worktree layouts whose
  `.git` is not a directory.
- It does not install or update consumer dependencies, declarations, or lock files.
- It does not rewrite consumer-owned native configuration during enroll or sync.
- It does not provide one global ignore list or let a consumer silently remove central gates.
- It does not auto-fix formatting or lint findings.
- It does not automate Codex hook trust or permission escalation.
- It does not provide host containment. Users can disable local hooks, and CI remains authoritative.
- It does not merge pull requests, close issues, create tags or releases, or publish packages
  unless a separately authorized external operation does that work.
- It does not create global plugin state, a global consumer list, global session history, hidden
  rollback generations, or a shared cross-repository breaker.
- It does not copy another repository's Git history.

## Troubleshooting

`repository deployment is stale`

: Run `qat repo status TARGET`, inspect which identity or path is stale, then run
  `qat repo sync TARGET`.

`selected executable is unavailable`

: Run `qat tool status` and rebuild with `./bootstrap.sh`. Use `qat tool fetch TOOL` only when a
  selected standalone payload or environment is missing.

`declared consumer path does not exist` or `is not tracked`

: Correct `.qat.toml`, add the declared files to Git, commit them, and enroll or sync again.

`refusing to replace foreign hook path`

: Inspect the existing hook. If adopting and later restoring it is intended, repeat enroll or sync
  with `--adopt-hooks`.

`configuration conflict; target unchanged`

: Inspect `.git/qat/conflicts/CONFIGURATION_ID`. Resolve the consumer-owned copy deliberately, then
  retry sync. Use `--hard-reset` only when discarding the local managed copy is intended.

A gate printed only `[FINDING]` without its diagnostic output

: Gate output is retained rather than echoed by the runner. Use `qat evidence show --target
  TARGET`, then open the referenced `.stdout` and `.stderr` files in the printed evidence
  directory.

## Repository layout

| Path | Purpose |
| --- | --- |
| `registry/tools.json` | Accepted tool versions, sources, assets, checksums, and executables. |
| `profiles/*.toml` | Complete tool, gate, hook, skill, severity, timeout, and order choices. |
| `config/` | Shared native tool configurations and locked Julia environments. |
| `corpus/vocabulary.toml` | Shared terminology and source-classification corpus. |
| `library/` | Hook entries, repository skills, retained instructions, and work templates. |
| `bin/qat-*` | Small utilities with one primary operation. |
| `src/qa_toolkit/` | Validation, deployment, runner, and command implementation. |
| `docs/foundation.md` | Detailed ownership, safety, CI, and foundation record. |

The `bin/qat` command is only a dispatcher to the small `bin/qat-*` utilities. Run
`qat --help` for the complete family list and `qat <command> --help` for exact arguments.
