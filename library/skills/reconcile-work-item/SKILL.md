---
name: reconcile-work-item
description: Recover a qa-toolkit work item from exact local and remote Git state; use when execution or publication was interrupted or identities may have drifted.
---

# Reconcile Work Item

Run `qat work status`, inspect the local HEAD and remote branch, then run `qat work reconcile`.

Reconciliation may publish a known provisional commit, bind the declared PR number, retry a final exact-lease publication, or confirm completion. It must not accept a different parent, branch, issue, PR, provisional SHA, or final SHA. Stop and report any mismatch instead of rewriting state or using an unbounded force push.

After recovery, report the structured phase and exact revisions.

