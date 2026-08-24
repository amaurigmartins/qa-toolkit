---
name: release-work-package
description: Calculate and prepare a separate release task after an implementation PR is merged; use only when the user explicitly requests release preparation.
---

# Release Work Package

Verify the implementation PR is merged before release preparation. Use `qat work release` with the accepted commit messages to calculate the minimum SemVer increment.

Create a distinct release work package and limit allowed paths to declared version files and release notes. The release PR may close the issue when the user requests it. Do not tag, create a GitHub release, or publish a package without separate explicit authorization. Keep those operations outside the implementation task.

