# General Post-Refactor Cleanup, Debloating, and Architectural Convergence Planning Prompt

You are working in **planning mode only**.

The repository has already undergone a substantial implementation or refactor sequence. The immediate goal is **not to add another feature layer, not to preserve every historical implementation choice, and not to redesign the system from first principles**.

Your task is to inspect the repository as it exists now and produce an evidence-based cleanup and convergence plan that makes the codebase smaller where possible, clearer, more cohesive, less redundant, easier to extend, and easier to reason about while preserving the behavior that is actually intended to remain stable.

This is a post-refactor convergence pass.

Do not modify source files in this session.

---

## 1. First reconstruct the repository truth

Do not begin from generic software-architecture advice.

Before proposing cleanup work, inspect enough of the repository to understand its own terminology, boundaries, lifecycle, architecture, validation practices, and development stage.

At minimum, inspect as applicable:

- `README*`;
- repository-level agent/instruction files such as `AGENTS.md`;
- `docs/`, architecture notes, design specifications, ADRs, developer guides, and maintained technical documentation;
- the current implementation plan, roadmap, task files, audit reports, or migration notes if present;
- public API definitions, schemas, configuration models, persistent formats, protocols, adapters, command-line interfaces, and extension points;
- tests, fixtures, integration tests, numerical baselines, and acceptance tests;
- CI, quality gates, lint/type-check configuration, and repository scripts;
- package/module layout and the actual dependency direction between major components;
- recent Git history and the commits that implemented the preceding refactor, when available;
- current `git status`, so unrelated user work is not accidentally folded into the cleanup plan.

If a prior planning-session transcript is supplied, read the complete transcript. Use it to recover rationale, rejected approaches, temporary migration decisions, and intended end-state architecture.

However, **do not treat the transcript as a cumulative specification**. Earlier ideas may have been superseded.

Resolve conflicts using this order:

1. explicit current user requirements and constraints;
2. the repository's current intended behavior and supported contracts;
3. current normative repository documentation;
4. the latest accepted architectural decisions in the planning history;
5. older plans, audits, proposals, and intermediate implementation decisions.

Tests are evidence, not automatically normative truth. A test can preserve an obsolete behavior just as efficiently as it can prevent a real regression.

Before planning, summarize the actual repository architecture using the project's own vocabulary.

---

## 2. Infer the project DSL instead of imposing one

Do not import a generic architecture vocabulary and force the repository into it.

Discover from the codebase:

- the main domain concepts;
- which objects or modules own them;
- persistent versus runtime state;
- public versus internal APIs;
- orchestration versus core logic;
- computational/numerical kernels;
- adapters and external boundaries;
- storage/filesystem/database/network boundaries;
- generated artifacts and derived state;
- lifecycle transitions;
- plugin, formulation, backend, mode, or feature extension mechanisms;
- error and validation boundaries;
- testing layers and acceptance mechanisms.

Use the names and conventions already established by the repository unless the cleanup specifically identifies a naming inconsistency worth correcting.

The purpose of this step is to understand what the system *is*, not what a generic architecture textbook thinks it ought to be.

---

## 3. Establish the preservation contract before proposing deletions

Determine what must remain behaviorally stable.

Preserve, unless the current repository requirements explicitly say otherwise:

- core domain semantics;
- numerical algorithms and numerical results;
- validated tolerances and numerical baselines;
- externally supported workflows;
- persistent data that is still part of the supported contract;
- output orientation, ordering, units, identities, and deterministic behavior where these are meaningful;
- intended lifecycle semantics;
- supported integration behavior;
- required safety, transaction, provenance, and validation guarantees;
- real bug fixes already established by the preceding work.

Do **not** automatically preserve:

- obsolete private APIs;
- intentionally renamed early-stage APIs;
- superseded schemas or names;
- compatibility aliases created only to protect an implementation that was never released or never promised stable;
- fallback readers for formats that no longer need support;
- historical behavior that was deliberately changed;
- temporary migration paths whose cutover is complete;
- tests whose only purpose is to freeze any of the above.

The project stage matters.

If the repository is explicitly prototype, pre-release, experimental, internal, or otherwise free to make breaking changes, do not manufacture backwards compatibility merely because a symbol changed. Compatibility has a maintenance cost and must have an actual supported consumer.

For each potentially breaking cleanup, determine whether a real compatibility obligation exists. Evidence can include released versions, external consumers, documented stability promises, persisted user data, interoperability contracts, or explicit user requirements.

"No evidence of a compatibility requirement" is not the same as "invent a compatibility layer just in case."

---

## 4. Audit architecture by responsibility, not by line count

The cleanup is not a code-golf exercise. LOC is a useful signal, not an objective function.

A larger implementation can be correct when the domain genuinely requires more behavior. A smaller implementation can still be an incomprehensible pile of compressed nonsense.

Evaluate whether the architecture has **one clear authority for each concept**.

For every major concept or behavior, identify:

- authoritative state;
- authoritative implementation;
- readers;
- writers;
- derived projections;
- adapters;
- validation;
- lifecycle owner;
- tests that establish its contract.

Flag cases where multiple independent mechanisms claim authority over the same thing.

Typical examples include:

- parallel old/new controllers;
- duplicated state representations;
- one value persisted in several places;
- several independent classifiers for the same semantic effect;
- a declarative registry that is validated but not actually used to drive runtime behavior;
- separate readers/restorers/publishers that duplicate one mapping;
- old and new API paths both remaining active;
- two serializers representing the same contract;
- multiple ways to dispatch the same operation.

The target is not "one giant function." The target is **one authority per concept, with explicit boundaries around it**.

---

## 5. Audit abstraction quality aggressively

Treat excess abstraction as a form of code bloat.

An abstraction earns its existence when it does at least one substantial job such as:

- owns a real domain invariant;
- isolates a genuine external boundary;
- compresses repeated policy;
- represents a stable domain concept;
- provides a meaningful protocol with multiple legitimate implementations;
- centralizes lifecycle or transaction semantics;
- removes material duplication;
- makes an extension point predictable and lower-cost.

Be suspicious of abstractions that only:

- rename another function call;
- forward arguments unchanged;
- wrap one implementation with no actual boundary;
- exist solely to satisfy a linter or stylistic rule;
- introduce factories, managers, registries, strategies, providers, adapters, or protocols without a demonstrated architectural responsibility;
- turn three direct lines into several classes and indirections;
- create generic infrastructure for hypothetical future features;
- make call flow harder to follow without reducing change amplification;
- duplicate an existing first-class abstraction under a different name.

Do not reflexively delete every helper or one-implementation protocol. Judge whether it owns a meaningful concept or boundary.

For each suspect abstraction, answer:

1. What invariant, policy, domain concept, or boundary does it own?
2. Which real duplication or coupling does it remove?
3. How many legitimate consumers or implementations use it?
4. What breaks conceptually if it is inlined or removed?
5. Would direct code be easier to understand and modify?
6. Does this abstraction reduce or increase the number of places changed for a normal feature?

If those questions have weak answers, plan its removal or collapse.

Do not replace one unnecessary abstraction with a newer, more fashionable unnecessary abstraction. Humans already invented enough ways to hide a function call.

---

## 6. Evaluate "uniformity" as conceptual consistency

Do not interpret uniformity as forcing identical syntax everywhere.

Uniformity means analogous concepts obey analogous rules unless their semantics genuinely differ.

Inspect whether similar concepts consistently use the same:

- ownership model;
- naming convention;
- lifecycle;
- state representation;
- error policy;
- validation boundary;
- persistence policy;
- extension mechanism;
- dispatch pattern;
- testing strategy;
- adapter boundary.

Legitimate domain-specific variation must remain.

Flag **accidental asymmetry**, where two equivalent concepts are implemented differently because they evolved independently rather than because the domain requires it.

A useful test is change predictability:

> If a developer adds one more object of an existing conceptual category, can they predict where the change belongs from the existing architecture?

If adding a normal field, mode, backend, formulation, entity, command, or workflow requires hunting through unrelated string comparisons, parallel registries, special cases, and duplicated mappings, the architecture has not converged.

---

## 7. Audit change amplification

For representative changes that are normal for this project, determine how many independent locations must be edited.

Examples should be derived from the repository's own DSL, such as:

- adding one field/property;
- adding one domain entity;
- renaming one early-stage API symbol;
- adding one analysis/backend/formulation/mode;
- adding one persisted value;
- adding one result product;
- changing one lifecycle state;
- adding one adapter or external integration.

Do not assume that "one file only" is always ideal. Some changes legitimately cross schema, domain model, implementation, and tests.

The problem is **unrelated or duplicated edits**.

Flag situations where a change must be repeated because the same semantic information is independently encoded in multiple places.

Prefer an architecture where each extension has a small, predictable set of edits with clear ownership.

---

## 8. Audit defensive coding at the correct boundaries

Do not equate more checks with more robustness.

Defensive code is justified in proportion to the uncertainty and trust level of the boundary.

Strong validation is normally justified around:

- untrusted external input;
- network/API boundaries;
- user-authored persistent data;
- filesystem paths and destructive operations;
- concurrency or process boundaries;
- foreign tools and subprocesses;
- irreversible transactions;
- versioned external formats;
- numerical validity conditions where failure would silently corrupt results.

Inside trusted internal flows, repeatedly revalidating states that are already guaranteed by construction can create more branches, more failure modes, and more maintenance burden than protection.

Identify:

- impossible-state guards that duplicate upstream invariants;
- repeated validation of the same value at every call layer;
- catch-and-wrap chains that add no information;
- fallback logic for unsupported or impossible states;
- retry/recovery paths with no actual recoverable boundary;
- transactional machinery around operations that do not need transactions;
- deep-copy/clone behavior motivated only by hypothetical mutation;
- broad exception handling hiding programming errors.

Do not remove safeguards merely because they are verbose. Tie every guard to the failure mode it prevents.

The objective is **boundary-proportional defense**, not optimism and not paranoia.

---

## 9. Audit compatibility and migration residue

Search specifically for:

- compatibility wrappers;
- aliases for renamed objects;
- deprecated names;
- fallback readers;
- dual schema versions;
- old/new path mirrors;
- migration adapters;
- shadow implementations;
- temporary bridge code;
- compatibility fixtures;
- "legacy" branches;
- TODO/FIXME notes describing completed migrations;
- tests that exercise only superseded behavior.

For each item classify it as:

- still required by a real supported compatibility contract;
- temporarily required because cutover is incomplete;
- obsolete and removable now;
- unclear and requiring evidence before removal.

Do not retain compatibility by default in early-stage projects.

Conversely, do not delete a real external contract merely because the code would look prettier without it.

---

## 10. Audit tests as architecture, not as sacred archaeology

Classify the important tests into categories such as:

- core invariant tests;
- numerical/scientific baselines;
- public contract tests;
- integration tests;
- end-to-end workflow tests;
- regression guards for a demonstrated bug;
- transaction/safety tests;
- compatibility tests;
- implementation-detail tests;
- redundant tests;
- tests preserving intentionally superseded behavior.

A regression test is useful when it protects a current invariant or a mistake likely to recur.

A regression test is not automatically useful forever merely because a bug once existed.

Determine whether old regression tests are now:

- still the best guard for a live invariant;
- subsumed by a stronger higher-level invariant;
- testing an implementation detail that no longer matters;
- preserving behavior deliberately changed during the refactor;
- duplicating broader integration coverage;
- constraining simplification without protecting supported behavior.

Where appropriate, replace narrow historical tests with stronger semantic tests.

Do not maximize test count.

Do not delete numerical baselines, integration evidence, or safety guards simply to obtain a smaller diff.

Tests should constrain the **current architecture and supported behavior**, not preserve every intermediate state the repository has ever survived.

---

## 11. Audit dependency boundaries and invalidation scope

Inspect whether operations depend only on what they actually consume.

Look for broad dependency sets such as:

- hashing or rebuilding unused objects;
- scanning entire libraries when only active references matter;
- invalidating expensive artifacts because unrelated configuration changed;
- copying whole workspaces for a local transaction;
- eager loading/parsing of unrelated data;
- broad cache invalidation;
- whole-tree state replay for local changes;
- hidden coupling through global registries or shared mutable state.

For each case, determine the actual transitive dependency closure.

A concept should normally be invalidated, rebuilt, copied, serialized, or recomputed only when one of its real inputs changes.

Do not introduce elaborate caching or incremental frameworks unless the repository demonstrates a real need. First fix incorrect dependency ownership.

---

## 12. Audit state and persistence

For every persisted or long-lived state value, ask:

- Is this authoritative state or derivable state?
- Is it stored more than once?
- Can two copies disagree?
- Is transient UI/runtime state leaking into persistent domain state?
- Is historical execution state being conflated with current authored state?
- Are multiple independent state axes compressed into one ambiguous status?
- Are IDs, hashes, markers, or caches still required after the refactor?
- Is temporary migration state still persisted after cutover?

Prefer storing authoritative and non-derivable state.

Derive presentation state, summaries, dirty flags, and status combinations when practical from authoritative inputs and explicit baselines.

Do not eliminate persisted evidence that is required for reproducibility, provenance, transaction safety, or external contracts.

---

## 13. Audit dead code and transitional residue

Use static inspection, references, call sites, tests, and repository history to find:

- unreachable code;
- private helpers with no remaining production caller;
- unused configuration;
- duplicate constants;
- shadow-mode code after cutover;
- old serializers/deserializers;
- obsolete adapters;
- stale feature flags;
- dead branches;
- duplicate utility functions;
- old fixtures;
- outdated docs that describe deleted architecture;
- comments explaining temporary constraints that no longer exist.

Do not classify code as dead only because a crude text search finds no local caller. Account for reflection, registration, plugin discovery, external entry points, tests, generated bindings, and language-specific dispatch.

Every deletion must be evidence-based.

---

## 14. Separate cleanup from intentional product refinement

Produce two clearly separated tracks.

### Track A — Behavior-preserving convergence

This is the main cleanup plan.

It may:

- remove redundancy;
- collapse unnecessary abstraction;
- delete obsolete compatibility;
- eliminate dead code;
- unify duplicated authority;
- simplify data flow;
- reduce change amplification;
- tighten dependency boundaries;
- replace obsolete tests with current invariant tests;
- reduce unnecessary defensive machinery;
- reconcile documentation with the actual architecture.

Track A must preserve the agreed core behavior, supported workflows, and numerical results.

### Track B — Intentional refinements

List only refinements discovered during the audit that would deliberately change supported behavior, API, semantics, algorithms, numerical behavior, workflow, persistent contract, or user experience.

Do not silently mix Track B into cleanup commits.

For each Track B candidate state:

- what would change;
- why it may be beneficial;
- what evidence motivates it;
- which contract or result would change;
- what new validation would be required.

Track B is advisory unless explicitly approved.

This separation prevents "cleanup" from becoming a convenient excuse for redesigning half the project.

---

## 15. Do not cargo-cult "clean architecture"

The cleanup plan must not introduce architecture for architecture's sake.

Unless repository evidence demands it, do not propose:

- a new framework;
- a new plugin system;
- dependency injection infrastructure;
- event buses;
- service locators;
- generic repositories;
- universal manager/factory layers;
- new `utils`, `common`, or `helpers` dumping grounds;
- broad module splitting solely because files are large;
- compatibility machinery for hypothetical consumers;
- a second abstraction layer whose only purpose is to remove the first abstraction layer.

A large file can be badly structured, but file length alone is not an architectural diagnosis.

Split or reorganize code only when ownership, dependency direction, independent change, testing, or navigation materially improves.

Use the language, framework, and repository idioms already present unless those idioms are themselves the diagnosed problem.

---

## 16. Required evidence for every cleanup finding

Every material finding in the plan must include:

- concrete file(s), module(s), symbol(s), or contract(s);
- the current responsibility;
- the observed problem;
- why the complexity is unnecessary, duplicated, obsolete, or misplaced;
- what supported invariant must remain;
- the proposed simplification;
- deletion/collapse opportunities;
- risk of the change;
- how the result will be validated.

Avoid vague findings such as:

- "architecture could be cleaner";
- "consider reducing coupling";
- "improve separation of concerns";
- "use better abstractions";
- "add more tests."

Name the actual coupling, authority collision, redundant layer, or unsupported compatibility path.

---

## 17. Planning discipline

Plan cleanup as a finite sequence of small, reviewable commits.

Each commit must have one coherent purpose and leave the repository valid.

Do not create a 20-commit ceremonial procession merely because granular plans look industrious. Equally, do not combine unrelated cleanup into one archaeological explosion.

For every commit provide:

- commit number;
- proposed subject;
- purpose;
- prerequisite;
- files/components likely affected;
- exact architectural change;
- code expected to be deleted, collapsed, or simplified;
- tests to delete, rewrite, retain, or add;
- explicit forbidden scope;
- validation commands discovered from the repository;
- completion criteria;
- observable before/after state;
- expected effect on implementation complexity.

Where possible, cleanup commits should be **net-negative in production complexity**, but do not game LOC counts. A small amount of new code is acceptable when it eliminates larger duplicated machinery or establishes one real authority.

No commit should add a generalized abstraction unless it demonstrably removes more conceptual duplication than it creates.

Sequence work so that replacement authority is proven before deleting the old authority, but delete transitional paths as soon as the cutover is established. Do not leave "temporary" compatibility for a mythical future cleanup phase.

---

## 18. Validation requirements

Discover the repository's actual validation commands from its documentation, scripts, CI, and tool configuration.

The plan should use the strongest relevant layers available, such as:

- unit tests;
- contract/schema tests;
- integration tests;
- real-tool acceptance tests;
- numerical/scientific baselines;
- end-to-end workflows;
- linting;
- formatting;
- type checking;
- static architecture checks;
- repository quality gates.

Do not invent commands.

Do not weaken existing tolerances, skip tests, regenerate baselines merely to match a changed implementation, or replace real integration coverage with mocks unless the change explicitly justifies that test redesign.

For scientific/numerical software, preserve numerical baselines independently from UI/API/architecture cleanup wherever possible.

---

## 19. Final convergence criteria

Define a finite end state for the cleanup.

Adapt the criteria to the repository, but explicitly evaluate whether the final codebase achieves the following principles:

### Authority

- One authoritative implementation per concept.
- No old/new parallel paths after cutover.
- No duplicated persistent state without a justified reason.
- No registry, schema, adapter, or protocol that is merely decorative.

### Abstraction

- Each nontrivial abstraction owns a real invariant, policy, domain concept, or boundary.
- Trivial forwarding layers and speculative extensibility are removed.
- Internal control flow is direct enough to follow without reconstructing a maze.

### Compatibility

- Compatibility exists only for supported consumers or persisted contracts.
- Early-stage renamed APIs do not retain aliases by reflex.
- Obsolete migration and fallback paths are gone.

### Testing

- Tests protect current behavior and invariants.
- Numerical/scientific baselines remain intact where required.
- Obsolete compatibility and superseded-behavior tests are removed or rewritten.
- Regression guards remain where the underlying failure mode is still meaningful.

### Dependencies

- Expensive operations depend only on their actual transitive inputs.
- Unrelated changes do not trigger rebuilds, invalidations, scans, copies, or state replays.

### State

- Authoritative state is clearly owned.
- Derivable state is not unnecessarily persisted.
- Independent state axes are not conflated.

### Extension cost

- Adding a normal domain concept follows a predictable path.
- Similar concepts use the same architectural pattern unless semantics justify variation.
- A developer does not need to edit unrelated parallel mappings to add one ordinary feature.

### Residue

- No dead migration scaffolding, shadow paths, stale compatibility wrappers, duplicate serializers, abandoned flags, or obsolete documentation remains.

### Scope

- Core supported behavior and numerical results remain unchanged under Track A.
- Any intentional refinements remain isolated under Track B.

---

## 20. Required output

Produce one complete Markdown planning document with this structure:

```text
# Post-Refactor Cleanup and Architectural Convergence Plan

## 1. Repository state and sources inspected
- current HEAD / branch / worktree state
- relevant documentation and instructions
- refactor history or transcript inspected
- validation commands discovered

## 2. Reconstructed architecture
- project-specific domain vocabulary
- major authorities and boundaries
- persistence/runtime/external/numerical layers
- current extension paths

## 3. Preservation contract
- behavior that must remain stable
- numerical/scientific invariants
- supported external contracts
- explicitly non-required legacy/compatibility behavior

## 4. Architectural findings
For each finding:
- evidence
- current responsibility
- problem
- invariant to preserve
- proposed simplification
- risk
- validation

## 5. Abstraction and redundancy audit
- justified abstractions
- suspect abstractions
- duplicate authorities
- forwarding/wrapper layers
- speculative infrastructure
- dead/transitional machinery

## 6. Compatibility and defensive-code audit
- required compatibility
- obsolete compatibility
- boundary-justified defenses
- redundant internal defenses

## 7. Test-suite audit
- core invariant tests
- numerical/integration baselines
- regression guards to retain
- regression tests to rewrite/delete
- compatibility-shaped or implementation-detail tests
- redundant coverage

## 8. Dependency, state, and performance audit
- actual dependency closures
- over-broad invalidation/rebuild/copy behavior
- duplicated/derivable state
- unnecessary hot-path work

## 9. Track A — Behavior-preserving convergence
- finite ordered cleanup commits

## 10. Track B — Intentional refinements
- clearly separated candidates only

## 11. Final convergence criteria
- concrete repository-specific end-state checks
```

For each Track A commit use:

```text
## Commit N — <short title>

Subject:
`<commit subject>`

Purpose:
<one coherent cleanup goal>

Evidence:
<concrete current symbols/files/behaviors motivating the commit>

Changes:
- ...

Delete/collapse:
- ...

Tests:
- retain:
- rewrite:
- delete:
- add only where required:

Forbidden:
- ...

Validation:
- repository-native commands only

Completion:
- ...

Observable change:
- Before:
- After:

Complexity effect:
- explain what conceptual machinery disappears or becomes singular
```

---

## 21. Hard prohibitions

Do not:

- edit the repository in this planning session;
- assume green tests imply clean architecture;
- assume more tests imply more safety;
- assume all regressions deserve permanent dedicated tests;
- preserve unreleased APIs by default;
- add compatibility aliases without a real consumer;
- infer quality from LOC alone;
- introduce abstractions just to satisfy style rules;
- split modules merely because they are large;
- create generic infrastructure for hypothetical future use;
- replace direct code with patterns whose only benefit is theoretical extensibility;
- delete genuine safety boundaries, numerical validation, provenance, or transaction guarantees for aesthetic simplicity;
- mix deliberate behavior changes into behavior-preserving cleanup;
- trust old plans more than the current repository;
- treat every existing test as an immutable specification;
- generate a plan from repository names alone without inspecting their implementations and call paths;
- recommend "cleanup later" for transitional code whose replacement authority is already proven.

The required result is not a prettier diagram.

The required result is a repository where the important concepts have obvious owners, normal changes have predictable scope, protections exist where real failure modes justify them, tests defend current invariants, and obsolete machinery has been removed rather than embalmed.
