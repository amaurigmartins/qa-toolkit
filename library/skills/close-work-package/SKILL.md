---
name: close-work-package
description: Finish and retire the explicit Sentinel cleanup task for a qa-toolkit work package when the accepted package is ready for human review.
---

# Close Work Package

Require an initialised cleanup task with `retire_after_finish = true` and Sentinel validation. Implement only its declared cleanup paths, run `qat work finish`, and confirm exact local and remote final SHAs.

Run `qat work retire` only after successful publication. Retirement removes only the local `.git/qat/work/<id>` state. It does not merge, close the issue, tag, release, or change hook trust. Mark a draft PR ready through `qat agent github pr-ready` only with authorisation.
