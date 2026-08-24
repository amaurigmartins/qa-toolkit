# qa-toolkit

Personal, repository-scoped quality tooling for Python, Julia, documentation, Git, and Codex.

This repository owns one central set of pinned tool payloads, configurations, vocabulary, hooks,
skills, workflows, and deterministic work-package utilities. Consumer repositories opt in through
a tracked `.qat.toml`. Enrollment deploys only repository-local links and state.

The toolkit is private personal tooling. It carries no compatibility, support, or suitability
promise for third-party use.

## Foundation status

The clean-slate foundation is under active construction on `refactor/foundation`. Until its
acceptance suite passes, do not use it to replace an existing repository's quality setup.

The intended command is `qat`. Runtime payloads remain below the ignored `toolkit/` directory.
Consumer evidence and guardrail state remain below that consumer's `.git/qat/` directory.
