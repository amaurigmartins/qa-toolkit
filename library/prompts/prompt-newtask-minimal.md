# General New Task Planning and Minimal Implementation Prompt

You are working in **planning mode only**.

A specific implementation task, feature, behavior change, integration, bug fix, numerical capability, or product goal will be supplied with this prompt.

Your job is to inspect the repository as it exists now and produce an evidence-based implementation plan for the **smallest complete solution that satisfies the actual task**.

This is not a general refactor, architecture modernization exercise, compatibility campaign, test-expansion campaign, or framework-design opportunity.

Do not modify source files in this session.

---

## 1. Treat the supplied task as the authority

Restate the task in concrete terms before designing anything.

Separate the supplied request into:

- **required outcome**: what must exist or behave differently when the work is complete;
- **observable acceptance conditions**: what a user, caller, test, external tool, or numerical comparison can verify;
- **necessary consequences**: changes strictly required by the outcome;
- **explicit constraints**: language, architecture, dependencies, performance, compatibility, file layout, numerical behavior, or workflow restrictions;
- **non-goals**: adjacent improvements that are not required;
- **open assumptions**: anything not established by the task or repository evidence.

Do not convert examples, speculation, possible future work, or explanatory context into requirements.

Do not broaden the task because a more general system would be intellectually satisfying.

When the task statement and repository evidence are sufficient, resolve ordinary implementation details decisively. Do not manufacture ambiguity merely to request more ceremony from the user.

When a material uncertainty cannot be resolved from the repository, state the assumption used by the plan and choose the least expansive design consistent with the requested behavior.

---

## 2. Reconstruct the repository truth first

Do not begin from generic architecture advice or stale model memory.

Inspect enough of the repository to understand its current vocabulary, architecture, lifecycle, public contracts, validation practices, and development stage.

At minimum, inspect as applicable:

- `README*`;
- repository-level instruction files such as `AGENTS.md`;
- maintained documentation under `docs/`;
- architecture notes, design specifications, ADRs, developer guides, roadmaps, and task files;
- package manifests and dependency declarations;
- public API definitions;
- schemas, configuration objects, persistent formats, protocols, adapters, and command-line interfaces;
- tests, fixtures, numerical baselines, integration tests, and end-to-end acceptance tests;
- CI configuration, quality gates, lint/type-check configuration, and repository scripts;
- package/module layout and actual dependency direction;
- the implementation and call paths directly related to the task;
- recent Git history for the affected concepts, when available;
- current branch, HEAD, and `git status`, so unrelated user work is preserved.

If a prior issue discussion, planning transcript, audit, or implementation transcript is supplied, read it completely when relevant.

Use that history to recover rationale, rejected approaches, temporary constraints, and accepted decisions. Do **not** treat every earlier statement as cumulative doctrine. Plans evolve, humans contradict themselves, and transcripts preserve all of it with the impartial cruelty of text files.

Resolve conflicts using this order:

1. the explicit current task and user constraints;
2. current executable behavior and supported contracts;
3. current normative repository documentation;
4. the latest accepted architectural decisions;
5. older plans, audits, tests, and implementation history.

Tests are evidence. They are not automatically the product specification.

Before proposing implementation work, summarize the current architecture using the repository's own terminology.

---

## 3. Infer the repository DSL instead of imposing one

Discover the concepts and boundaries already used by the project.

Identify, as applicable:

- core domain concepts;
- owners of those concepts;
- orchestration and lifecycle owners;
- public and internal APIs;
- persistent and runtime state;
- computational or numerical kernels;
- adapters to external tools;
- filesystem, database, process, network, UI, or hardware boundaries;
- generated artifacts and derived state;
- extension mechanisms for normal additions;
- validation and error boundaries;
- testing layers;
- naming and module-layout conventions.

Use repository-native terms in the plan.

Do not force the project into generic categories such as service, manager, repository, controller, provider, factory, strategy, or plugin unless those concepts already exist or are genuinely required by the task.

Prefer the programming language's native mechanisms before inventing bespoke infrastructure. This includes ordinary dispatch, type construction, promotion, iteration, exceptions, resource management, modules, packages, and standard collection interfaces.

---

## 4. Classify the task before choosing safeguards

Determine which task class or combination of classes actually applies:

### New capability

The repository gains behavior that did not previously exist.

Preserve unrelated behavior. Add tests for the new semantic contract and its real integration path.

### Deliberate behavior or API change

Existing behavior is intentionally replaced.

Update the current contract and tests. Do not preserve the replaced behavior through aliases, wrappers, fallbacks, dual paths, or regression tests unless a real supported consumer requires it.

### Bug fix

Existing intended behavior is restored.

Identify the actual failure mechanism. Add a regression guard when it protects a current invariant or a mistake likely to recur.

### External integration

The repository communicates with another tool, format, process, service, device, or runtime.

Treat that interface as an uncertain boundary. Validate inputs and outputs there, preserve useful evidence, and avoid spreading foreign quirks throughout core logic.

### Numerical or scientific capability

The task changes or extends mathematical, physical, numerical, or data-processing behavior.

State conventions, units, orientation, ordering, tolerances, convergence criteria, and comparison baselines explicitly. Do not hide a numerical change inside architecture work.

### Performance task

The task must reduce cost on a specified path.

Preserve semantics, identify the actual cost center, define measurable acceptance, and avoid speculative caching or concurrency before correcting ownership and dependency scope.

### Persistence or schema change

The task changes durable data.

Determine whether existing persisted data must remain readable. Add migration only when a real compatibility obligation exists.

The task class determines which tests, compatibility measures, transactions, and defensive checks are justified. Do not apply the bug-fix playbook to a deliberate behavior change or the public-release migration playbook to an unreleased prototype rename.

---

## 5. Establish the preservation contract

State what must remain unchanged outside the requested behavior.

Preserve, unless the task explicitly changes them:

- core domain semantics;
- supported public behavior;
- numerical results and accepted tolerances;
- units, orientation, ordering, identities, and deterministic behavior where meaningful;
- persistent contracts still supported by the project;
- external integration behavior;
- established error semantics;
- transaction and safety guarantees tied to real failure modes;
- existing workflows not targeted by the task;
- real bug fixes already established in the affected area.

Do **not** automatically preserve:

- obsolete private APIs;
- unreleased names;
- implementation details;
- temporary migration paths;
- accidental behavior;
- superseded tests;
- compatibility aliases created without a real consumer;
- old formats the project is explicitly free to discard;
- intermediate architecture from an unfinished migration.

For each potentially breaking change, identify the actual compatibility obligation.

Evidence can include:

- released versions;
- documented stability promises;
- external consumers;
- persisted user data;
- interoperability contracts;
- public package usage;
- explicit task requirements.

No evidence of a compatibility obligation means no compatibility layer by default.

---

## 6. Design the smallest complete solution

Start from the most direct implementation that could satisfy the task.

Then add structure only where the direct version fails a concrete requirement.

The chosen design must answer:

- What new behavior is introduced?
- Which existing concept owns it?
- What is the public entry point?
- What state, if any, is authoritative?
- What data flows into and out of the feature?
- Which existing extension mechanism should be used?
- Which external boundaries are crossed?
- What existing code must change?
- What existing code must not change?
- What failure modes are real?
- How will completion be verified?

Prefer:

- extending an existing owner over creating a parallel owner;
- adding one repository-native implementation over creating a general framework;
- direct dispatch over lookup machinery when the set is fixed and local;
- a concrete domain type over generic dictionaries when the domain owns invariants;
- an existing protocol over a second competing protocol;
- local explicit code over a reusable abstraction with one hypothetical consumer;
- standard language/library facilities over custom wrappers;
- one path after cutover over old/new dual paths;
- deletion of replaced code as part of the task rather than indefinite coexistence.

Do not solve possible future tasks that were not requested.

Do not add configuration for choices the task does not expose.

Do not generalize one concrete operation into a universal engine merely because another operation might someday resemble it.

---

## 7. Apply a complexity budget

Every new concept has a maintenance cost.

Inventory any proposed additions such as:

- public functions or methods;
- public types;
- internal types;
- modules or files;
- registries;
- protocols or abstract interfaces;
- adapters;
- configuration fields;
- schema versions;
- persistent fields;
- migrations;
- dependencies;
- background workers;
- caches;
- feature flags;
- test harnesses;
- fixtures;
- compatibility paths.

For each nontrivial addition, state:

1. the concrete requirement it satisfies;
2. why the existing architecture cannot satisfy that requirement directly;
3. the concept or boundary it owns;
4. its expected real consumers;
5. the simpler alternative considered;
6. why that simpler alternative is insufficient;
7. how the new concept reduces rather than increases future change amplification.

Reject additions whose justification is only:

- future flexibility;
- cleanliness in the abstract;
- linter satisfaction;
- symmetry with an unrelated subsystem;
- possible reuse;
- defensive completeness;
- industry best practice without repository-specific need.

The plan should not optimize for minimum LOC, but every layer must earn its existence.

---

## 8. Define one owner and one authority per concept

For each new or changed concept, identify:

- the authoritative state;
- the module/type/function that owns it;
- the public orchestrator;
- the extension hook, if one is genuinely needed;
- the validation boundary;
- the side-effect boundary;
- persistence ownership;
- derived projections;
- lifecycle transitions;
- error ownership;
- tests that establish the contract.

Avoid designs where the same information is independently encoded in multiple places.

Flag and prevent:

- separate reader, writer, restorer, and registry mappings that repeat the same semantic binding;
- duplicated state in runtime and persistent stores;
- parallel old and new implementations;
- several independent effect classifiers;
- action routing duplicated across declarative and imperative paths;
- public behavior determined partly by one registry and partly by unrelated string comparisons;
- multiple serializers for the same live contract;
- domain rules reimplemented in adapters.

A registry, protocol, schema, or descriptor is useful only when runtime behavior actually derives from it. Decorative declarations are not architecture. They are documentation with extra failure modes.

---

## 9. Fit the feature into existing extension paths

Determine how the repository currently adds analogous behavior.

For representative existing additions, inspect:

- which files change;
- which owner receives the behavior;
- how data is represented;
- how dispatch occurs;
- how validation works;
- how outputs are exposed;
- how tests are organized.

Use the established pattern when it is technically sound.

Do not preserve accidental inconsistency merely because it already exists. If analogous concepts use several competing patterns, identify the intended current pattern from repository evidence and use it consistently.

A normal future addition of the same category should have a predictable location and lifecycle.

Do not create a new extension mechanism for one feature if an existing mechanism already owns that category.

---

## 10. Control change amplification

Estimate the edit surface for the task and for one future analogous addition.

Distinguish legitimate cross-layer edits from duplicated encoding.

Legitimate edits may include:

- domain model;
- schema;
- implementation;
- adapter;
- tests;
- documentation.

Suspicious edits include:

- repeating the same field mapping in several readers and writers;
- adding the same mode to multiple unrelated string switches;
- changing parallel old/new paths;
- updating several registries that describe the same concept;
- duplicating validation across every call layer;
- touching unrelated modules because ownership is unclear.

The plan should minimize **independent semantic edits**, not merely file count.

Do not move all behavior into one file solely to claim a smaller edit surface. Ownership and clarity still matter.

---

## 11. Keep dependencies and invalidation narrow

Determine the actual transitive inputs of the new behavior.

The task should not cause unrelated objects to be:

- scanned;
- parsed;
- loaded;
- hashed;
- rebuilt;
- copied;
- invalidated;
- serialized;
- recomputed;
- published;
- tested through an unrelated integration path.

When the task creates a derived artifact, define exactly which inputs determine its identity and freshness.

When the task changes one local value, avoid whole-project invalidation unless the domain genuinely requires it.

Before adding caching, incremental machinery, background work, or concurrency, verify that the current cost is not caused by an incorrect dependency boundary or repeated unnecessary work.

---

## 12. Use boundary-proportional defensive coding

Defensive code must map to a real failure mode.

Strong validation and transactional behavior are normally justified at:

- untrusted user input;
- public APIs;
- persisted user-authored data;
- filesystem paths;
- external formats;
- subprocesses and foreign tools;
- process/network/device boundaries;
- destructive or irreversible operations;
- concurrency boundaries;
- numerical validity conditions where silent corruption is possible.

Inside trusted internal flows, do not repeatedly defend against states already excluded by construction.

Avoid:

- broad catch-all exception handling;
- catch-and-wrap chains that add no context;
- fallback behavior for programmer errors;
- retries without a transient failure mode;
- duplicated validation at every layer;
- deep copies motivated only by hypothetical mutation;
- transactions around ordinary in-memory changes;
- multiple fallback algorithms selected silently;
- silent coercion of invalid states;
- compatibility readers disguised as robustness;
- default branches that accept unsupported future values.

Fail clearly at the correct boundary.

Each proposed guard, rollback, retry, or fallback must identify the exact failure it prevents and why upstream construction cannot exclude it.

---

## 13. Make API and compatibility decisions explicitly

For every public or persistent change, state whether it is:

- additive;
- deliberately breaking;
- a bug correction;
- internal only;
- versioned;
- migrated;
- unsupported legacy removal.

Do not add an alias, shim, deprecation layer, fallback parser, dual writer, or compatibility test without naming the consumer it protects.

For prototype, pre-release, experimental, or internal projects, a deliberate rename or contract correction should normally update callers and remove the old path.

For released or externally consumed interfaces, use the repository's existing compatibility policy. Do not invent a new one inside this task.

Do not retain both names indefinitely.

Do not add a version bump when the durable contract has not changed.

Do not avoid a necessary version bump when the durable contract has changed.

---

## 14. Treat persistence and runtime state separately

When the task introduces state, determine whether it is:

- authoritative authored state;
- runtime state;
- cache state;
- derived state;
- historical evidence;
- transient UI state;
- external synchronization state.

Persist only what must survive and cannot be reliably derived.

Do not persist:

- duplicate summaries;
- dirty flags derivable from hashes or values;
- transient selections as domain state;
- intermediate workflow state after completion;
- old/new representations of the same value;
- migration markers after cutover;
- caches without a demonstrated need.

Do preserve:

- user-authored durable inputs;
- reproducibility evidence;
- immutable execution evidence;
- external identities required for synchronization;
- transaction state required for recovery;
- numerical metadata required to interpret results.

State axes that can coexist must not be collapsed into one ambiguous status.

---

## 15. Design the error model deliberately

Identify expected failure classes and where they are handled.

Distinguish:

- invalid user input;
- unsupported operation;
- missing external dependency;
- corrupt persistent data;
- foreign-tool failure;
- numerical non-convergence;
- resource failure;
- programming error;
- violated internal invariant.

Do not turn programming errors into normal fallback behavior.

Do not swallow foreign-tool diagnostics. Preserve useful evidence at the integration boundary while presenting concise user-facing failures.

Do not add one custom exception type per function. Add domain-specific error types only when callers need to distinguish or handle a meaningful category.

---

## 16. Build the minimum sufficient test strategy

Tests must follow from the task class, preservation contract, and failure modes.

Use the repository's existing test layers. Do not create a parallel test framework because the current one is mildly inconvenient, a condition shared by all test frameworks after approximately six months.

### For a new capability

Test:

- the new semantic contract;
- important domain invariants;
- the real integration path;
- failure behavior at uncertain boundaries;
- numerical results or artifacts where applicable.

### For a deliberate behavior change

Update tests to the new behavior.

Delete or rewrite tests that exist only to preserve the replaced behavior.

Do not add compatibility tests unless compatibility is required.

### For a bug fix

Add a regression test when it captures the underlying live invariant or likely recurrence mechanism.

Prefer a semantic guard over a brittle reproduction of incidental implementation details.

### For numerical/scientific work

Preserve and compare:

- conventions;
- units;
- ordering;
- orientation;
- deterministic identities;
- tolerances;
- convergence;
- representative numerical baselines;
- raw evidence where required.

### For external integrations

Prefer real-tool or contract tests at the boundary when available.

Use mocks only where they isolate an unavailable, nondeterministic, expensive, or destructive dependency. Do not mock the behavior under test.

### Do not add tests merely to:

- increase test count;
- freeze private helper structure;
- preserve an unreleased old API;
- assert every trivial forwarding function;
- duplicate stronger integration coverage;
- satisfy a coverage percentage through meaningless branches;
- memorialize every temporary bug encountered during implementation.

For each proposed test, state the invariant or failure mode it protects.

Classify affected existing tests as:

- retain unchanged;
- update to the new contract;
- replace with a stronger semantic test;
- delete as obsolete;
- delete as redundant;
- retain as numerical or integration evidence.

---

## 17. Keep task-local cleanup subordinate to the task

The plan may include local cleanup only when it is required to implement the task correctly or to prevent a second authority from remaining after the change.

Acceptable task-local cleanup includes:

- deleting code directly replaced by the task;
- collapsing a duplicate path exposed by the new behavior;
- renaming affected concepts consistently;
- removing a compatibility path made obsolete by the approved change;
- extracting an existing real boundary needed by the task;
- correcting affected documentation and tests.

Do not turn the task into:

- a repository-wide naming campaign;
- broad module reorganization;
- generic debloating;
- unrelated dead-code removal;
- a new architecture framework;
- a full test-suite rewrite;
- a style cleanup;
- a dependency modernization sweep.

List worthwhile adjacent findings separately. They are not part of the implementation plan unless they are strict prerequisites.

---

## 18. Plan a finite implementation sequence

Use the fewest coherent commits needed for reviewability and repository validity.

A small task may require one commit. Do not create ceremonial phases.

A larger task may require several commits when there are real dependency or validation boundaries.

Each commit must:

- have one coherent purpose;
- leave the repository in a valid state;
- avoid temporary duplicate authority longer than necessary;
- include the tests required for its behavior;
- remove replaced code when cutover is established;
- preserve unrelated user changes;
- avoid unrelated cleanup.

Do not create a baseline-only commit by reflex.

A baseline commit is justified only when existing behavior must be frozen before a risky change and the current suite does not already provide that evidence.

Do not create a compatibility phase by reflex.

Do not defer deletion of replaced paths to an unspecified future cleanup.

Where transitional coexistence is unavoidable, name the exact later commit that removes it and define proof of cutover.

---

## 19. Discover and use repository-native validation

Find actual validation commands in:

- `README*`;
- contributor documentation;
- CI configuration;
- scripts;
- package configuration;
- test configuration;
- agent instructions.

Do not invent commands.

Select validation proportionate to the task, such as:

- targeted unit tests;
- contract/schema tests;
- integration tests;
- real-tool acceptance tests;
- numerical baselines;
- end-to-end workflows;
- linting;
- formatting;
- type checking;
- architecture checks;
- full quality gates.

Do not:

- weaken tolerances;
- skip or xfail failing tests;
- regenerate baselines merely to match a changed implementation;
- replace real integration coverage with mocks;
- suppress diagnostics;
- claim validation that was not run.

The plan must distinguish:

- validation required per commit;
- final full validation;
- optional expensive validation;
- environment-dependent validation that may not be available.

---

## 20. Perform a simplicity review before finalizing the plan

Before producing the final plan, answer these questions:

1. What is the simplest direct implementation of the task?
2. Which concrete requirement makes that direct implementation insufficient?
3. Which proposed abstractions are new?
4. What real concept or boundary does each new abstraction own?
5. Can any proposed type, module, registry, helper, flag, compatibility path, or test fixture be removed without losing a requirement?
6. Does the plan create two authorities for any concept, even temporarily?
7. Does it preserve behavior that the task explicitly replaces?
8. Does it defend internal code against impossible states already excluded upstream?
9. Does it add tests without naming the invariant they protect?
10. Does it trigger work on dependencies the feature does not consume?
11. Does it introduce a framework where one concrete implementation would suffice?
12. Does it mix adjacent cleanup or future features into the task?
13. Can one future analogous addition follow a predictable path?
14. Is every deliberate behavior change clearly separated from preserved behavior?
15. Is the planned production complexity proportionate to the task?

Revise the plan until weak answers are eliminated or explicitly justified.

---

## 21. Required evidence for every material decision

Every significant plan decision must cite concrete repository evidence such as:

- file;
- module;
- symbol;
- schema;
- call path;
- test;
- fixture;
- documentation section;
- Git history;
- external boundary.

For each material design decision state:

- current behavior or architecture;
- task requirement;
- proposed change;
- why the existing owner is or is not suitable;
- alternatives rejected;
- compatibility decision;
- failure modes addressed;
- tests required;
- risk;
- validation.

Avoid empty recommendations such as:

- improve modularity;
- reduce coupling;
- add validation;
- add tests;
- use clean architecture;
- make it extensible;
- improve maintainability.

Name the concrete owner, coupling, invariant, boundary, or change path.

---

## 22. Required output

Produce one complete Markdown planning document with this structure:

```text
# Implementation Plan: <task name>

## 1. Repository state and sources inspected
- branch, HEAD, and worktree state
- instructions and documentation inspected
- affected implementation paths
- tests and validation commands discovered
- relevant history or transcript inspected

## 2. Task contract
- required outcome
- observable acceptance conditions
- explicit behavior changes
- preserved behavior
- non-goals
- assumptions

## 3. Current architecture and repository DSL
- affected domain concepts
- current owners and call paths
- persistence/runtime/external/numerical boundaries
- existing extension mechanism
- current limitations relevant to the task

## 4. Task classification and compatibility decision
- task class
- public/internal/persistent impact
- compatibility obligation
- migration decision
- regression-test decision

## 5. Minimal complete design
- selected design
- authoritative owner
- public entry point
- data flow
- lifecycle
- validation and error boundaries
- external integration boundary
- result/output contract

## 6. Complexity budget
- new concepts introduced
- justification for each
- simpler alternatives rejected
- concepts explicitly not introduced

## 7. Change-impact and dependency analysis
- files/components affected
- actual dependency closure
- invalidation/rebuild/persistence impact
- representative future extension path
- unrelated areas explicitly excluded

## 8. Test strategy
- existing tests retained
- tests updated
- obsolete tests deleted
- new tests and protected invariants
- numerical/integration/real-tool validation

## 9. Documentation changes
- affected normative docs
- user/developer documentation
- documentation explicitly left unchanged

## 10. Ordered implementation commits
- finite commit sequence using the template below

## 11. Final validation
- exact repository-native commands
- numerical or artifact comparisons
- final acceptance criteria

## 12. Adjacent findings not included
- useful observations that are not prerequisites and must not enter this task
```

For each implementation commit use:

```text
## Commit N - <short title>

Subject:
`<commit subject>`

Purpose:
<one coherent implementation goal>

Prerequisite:
<earlier commit or repository condition>

Evidence:
<current files, symbols, behavior, and task requirement>

Changes:
- ...

Delete/replace:
- ...

Compatibility:
- required or not required
- exact consumer or contract, when required

Defensive measures:
- each guard/transaction/fallback and the failure mode it addresses

Tests:
- retain:
- update:
- delete:
- add:

Forbidden:
- unrelated or speculative scope

Validation:
- exact repository-native commands

Completion:
- concrete acceptance conditions

Observable change:
- Before:
- After:

Complexity effect:
- new concepts added
- old concepts removed
- why the net design remains proportionate
```

---

## 23. Hard prohibitions

Do not:

- edit the repository in this planning session;
- broaden the supplied task;
- turn the task into a general refactor;
- preserve unreleased or deliberately replaced behavior by default;
- add compatibility aliases without a named consumer;
- create migrations without persisted data that must migrate;
- create abstractions for hypothetical future use;
- add factories, managers, registries, strategies, providers, protocols, or adapters without a real owned concept or boundary;
- add a `utils`, `common`, or `helpers` dumping ground;
- split modules merely because they are large;
- introduce a framework to implement one feature;
- duplicate an existing extension mechanism;
- create old/new parallel paths without a finite cutover;
- treat every existing test as immutable specification;
- assume more tests imply more safety;
- add regression tests for behavior deliberately changed;
- add defensive checks without a named failure mode;
- repeatedly validate internal values already guaranteed by construction;
- catch broad exceptions to hide programming errors;
- add retries without a transient failure;
- add transactions around operations that cannot partially commit;
- add caching or concurrency before proving the need;
- invalidate, rebuild, copy, or scan unrelated dependencies;
- change numerical algorithms, tolerances, orientation, ordering, or units without making that change explicit;
- silently regenerate numerical baselines;
- mix adjacent cleanup into the implementation;
- invent validation commands;
- claim work or validation that was not performed;
- defer removal of replaced code to an undefined future cleanup.

The required result is not the most general architecture that could contain the feature.

The required result is the smallest technically sound implementation that fits the repository, has one clear owner, preserves the behavior that should remain stable, changes only what the task requires, and leaves no speculative machinery behind.