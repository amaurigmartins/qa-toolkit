# qa-toolkit

Repository-scoped quality tooling for Python, Julia, documentation, Git, and Codex.

In all honesty, this is just yet another hoard of tooling that I scavenged like a spelunking goblin.

This repository owns one set of pinned tool payloads, configurations, vocabulary, hooks, skills,
workflows, and deterministic work-package utilities. A consumer opts in through a tracked
`.qat.toml`. Enrollment creates only repository-local links and state.

## Install the central bundle

Linux x86_64, POSIX `sh`, Git, an HTTPS downloader, archive tools, and a SHA-256 utility are the
only bootstrap requirements.

```console
./bootstrap.sh
bin/qat tool status
```

The bootstrap installs every accepted runtime below the ignored `toolkit/` directory. It does not
write a consumer dependency file. `./bootstrap.sh --link-launcher` may create the sole optional
path outside this repository: `~/.local/bin/qat`, linked to the tracked launcher.

## Enrol a repository

Track a `.qat.toml`, then select its complete profile:

```toml
schema_version = 1
profile = "disposable-python"
native_configurations = ["pyproject.toml"]
protected_paths = ["src", "tests"]

[vocabulary]
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
```

Validate and enrol it from this checkout:

```console
bin/qat profile validate disposable-python
bin/qat repo enroll /path/to/consumer
bin/qat repo status /path/to/consumer
bin/qat hook status /path/to/consumer
```

Enrollment creates ignored `.qat/` links, an exact ownership record under `.git/qat`, selected
repository-local skills, and repository-local Git and Codex dispatchers. Review and trust the exact
`.codex/hooks.json` through Codex `/hooks`. The toolkit never grants that trust.

A declared vocabulary file may use schema 1 for terminology, roles, acronyms, and bounded
allowances. Schema 3 additionally defines callable grammars, path-specific role ownership,
identifier replacements, and accepted and rejected examples. The runner validates that policy,
generates the shared text inputs from it, and adds one semantic Python gate.

The shared corpus defaults to US English (`en-US`). A repository may select `en-GB` explicitly in
its vocabulary file with `[settings] locale = "en-GB"`.

Restrict Vale prose analysis to bounded tracked paths when a repository needs only one document
class:

```toml
[text.prose]
include = ["**/*.tex"]
exclude = ["papers/quoted-sources/**"]
```

Without this declaration, Vale retains its default selection of Markdown, LaTeX, Python
docstrings, and Julia docstrings. `exclude` removes matching tracked paths after `include` or the
default selection. Both lists use bounded repository-relative patterns. The declaration changes
Vale inputs only. Spelling remains independently controlled through the repository vocabulary.

Profiles deploy `minimal-task-preflight` for an explicit repository-task review. The skill reads
small exact excerpts from the retained general planning prompt according to the task. It does not
load the complete prompt or run automatically.

Profiles that scan package prose also deploy the explicit-only `review-technical-prose` skill.
Invoke `$review-technical-prose` when a manual review is wanted. It runs the advisory QAT plan,
reads the `text-ai-tells` evidence, and loads the central writing guide only after evidence exists.
The skill judges findings in `docs/` and package docstrings. Ordinary coding does not load the
guide.

The `linecablemodels` profile uses Julia 1.12.6 and invokes the repository's default and
`tag:quality` test selections. Its consumer declaration should bind the native Julia inputs:

```toml
schema_version = 1
profile = "linecablemodels"
native_configurations = [
  "Project.toml",
  ".JuliaFormatter.toml",
  "test/runtests.jl",
  "test/quality/aqua.jl",
]
protected_paths = ["src", "ext", "test", "docs"]

[vocabulary]
additions = []
allowances = []

[work]
state_directory = ".git/qat/work"
require_allowed_paths = true
```

The Aqua dependency, tagged test, and portable Julia CI remain in LineCableModels. The toolkit
supplies the accepted runtime and invokes that repository-owned test. It does not run a second
Aqua rule.

Julia profiles also deploy two explicit-only skills. `julia-structural-design` routes structural
implementation through native-first admission before ownership and dispatch doctrine.
`julia-convergence-review` applies those doctrines during a post-refactor audit. A deterministic
reader emits only named heading-bounded excerpts from the untouched central sources. Neither skill
loads a complete playbook or runs automatically.

## Run quality gates

```console
bin/qat check --target /path/to/consumer
bin/qat sentinel --target /path/to/consumer
bin/qat sentinel --target /path/to/consumer --variant full
bin/qat advisory --target /path/to/consumer
```

`check` runs each selected fast gate once. `sentinel` runs that fast plan once, then each additional
Sentinel gate once. `--advisory` includes advisory gates in either plan without making their
findings blocking. An advisory execution failure still exits with status 2.

Exit status `0` means no blocking findings, `1` means at least one blocking finding, and `2` means
the configuration or execution failed. Every run retains its complete output below the consumer's
`.git/qat/evidence/` directory.

## Render Mermaid PDFs

The optional documentation utility renders every `.mmd` file below an explicitly selected source
directory with the Mermaid CLI 11.16.1 container image pinned by digest. It preserves relative
paths and skips outputs whose source content and renderer identity are unchanged.

```console
qat docs mermaid --source /path/to/repository/diagrams
qat docs mermaid --source diagrams --target rendered --engine podman
```

When `--target` is omitted, output goes to `SOURCE/mermaid-pdf`. Podman is preferred when both
Podman and Docker are available. `--force` renders every source again. This command is not selected
by a profile, bootstrap, enrollment, `check`, or `sentinel`. On first use, the selected container
engine may retrieve the pinned image into its own image storage.

## Sync, toggle, and remove

```console
bin/qat repo sync /path/to/consumer
bin/qat hook disable /path/to/consumer --kind git --event pre-commit
bin/qat hook enable /path/to/consumer --kind git --event pre-commit
bin/qat repo unenroll /path/to/consumer --backup /chosen/backup
```

Sync refreshes links and merges a copied managed configuration against its recorded base. It never
rewrites repository-owned native configuration. A merge conflict leaves the target unchanged and
stores the inputs below `.git/qat`. Only `--hard-reset` may discard a changed managed copy.

Unenrollment removes exact recorded paths and local-exclude entries. It retains `.qat.toml` and
native configuration by default. Use `--purge-config` only when those tracked declarations should
also be removed.

## Command families

The tracked `bin/qat-*` utilities each perform one operation. `bin/qat <group> <operation>` only
dispatches to those utilities.

| Family | Operations |
| --- | --- |
| Tools | `tool list`, `tool status`, `tool fetch`, `tool update` |
| Repositories | `profile validate`, `repo enroll`, `repo sync`, `repo status`, `repo unenroll` |
| Hooks | `hook enable`, `hook disable`, `hook status`, `hook dispatch` |
| Gates | `check`, `sentinel`, `advisory`, `commits` |
| Text | `corpus build` |
| Documentation | `docs mermaid` |
| Evidence | `evidence show`, `evidence export` |
| Work packages | `work init`, `stage`, `bind`, `reconcile`, `finish`, `report`, `retire`, `release` |
| Agent helpers | `agent github`, `agent thread-name` |

See [the foundation record](docs/foundation.md) for directory ownership, profile rules, update
behavior, work-package state, CI use, and the foundation audit.
