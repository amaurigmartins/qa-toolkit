---
name: review-technical-prose
description: Review QAT prose advisories for package documentation and docstrings. Use only when the user explicitly requests this skill, not for ordinary coding or general user-facing prose.
---

# Review Technical Prose

Review tracked package documentation and reader-facing docstrings without widening the task to
other prose. Unless the user names a narrower scope, inspect Markdown and LaTeX below `docs/` and
Python or Julia docstrings in package source. Do not include README files, issue text, commit
messages, comments, or conversational responses unless the user requests them.

1. Confirm that the target is enrolled and current with `qat repo status TARGET`. If it is not,
   report that state instead of substituting an unowned linter command.
2. Run `qat advisory --target TARGET`. This runs advisory gates only. Read the retained output for
   `text-ai-tells`; do not treat unrelated advisory findings as prose findings. Stop and report an
   execution error instead of interpreting missing output.
3. After obtaining the findings, read [writing guidelines](references/writing-guidelines.md).
   Apply them only to the requested review scope. The deterministic gate locates candidates; the
   guide determines whether each candidate weakens the technical prose.
4. Classify each applicable item as a real defect, an acceptable technical use, or a tool false
   positive. Report real defects with file, line, brief reason, and the smallest direct correction.
   Do not demand a zero-finding result when a flagged term is technically precise.

Treat equations, notation, units, citations, source behavior, and scientific meaning as fixed
unless the user separately authorizes changes to them. Preserve correct repeated terminology and
code examples. Do not turn stylistic preference into a technical finding.

If the user requests a review, remain read-only. If the user requests corrections, edit only the
approved prose scope, rerun `qat advisory --target TARGET`, and report any accepted remaining
findings. Do not run `qat check`, `qat sentinel`, change QAT policy, or add vocabulary exceptions
unless the user asks for those separate actions.
