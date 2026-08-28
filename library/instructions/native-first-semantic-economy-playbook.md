# Native-First Semantic Economy Playbook for Julia

## Abstraction admission, helper discipline, shim control, and mechanical anti-bloat policy

> **Use the language first. Use direct owner code second. Introduce a new semantic authority only when it adds meaning that no existing authority owns.**

## Status and scope

This document defines a repository-wide policy for deciding whether a new abstraction deserves to exist.

It targets Julia packages and applications, although the central rule is language-independent: use the native semantic mechanisms of the language and its established dependencies before inventing project-owned vocabulary. A non-Julia repository may apply the same admission procedure after substituting its own language protocols for the Julia-specific examples.

This is a **general principles playbook**, not an audit of any repository snapshot. It contains no claim that a retained source file, old branch, test, prompt, generated guide, or remembered implementation is correct. Concrete examples in this document are synthetic illustrations. They do not establish repository doctrine.

A repository applies this playbook through a separate, current, commit-scoped profile that records:

- the live preservation contract;
- current owners and public actions;
- established native and dependency interfaces;
- proven compatibility obligations;
- approved external workarounds;
- repository-native validation commands;
- project-specific residue searches.

Historical code may explain how a defect arose. It does not authorize repetition.

This playbook composes with two companion policies:

1. **Native-First Semantic Economy** decides whether a concept or abstraction may exist.
2. **Ownership-Centered Recursive Module Layout** decides who owns an admitted concept and where it lives.
3. **Dispatch-Driven Template Method** structures an admitted first-class action when its choreography is stable and some stages genuinely vary.

The order is strict. A concept rejected at step 1 does not become legitimate because it can be placed neatly in a module or expressed through elegant dispatch. Organized bloat remains bloat, merely alphabetized.

---

## 1. Normative precedence

### 1.1 Sources of authority

Resolve design conflicts in this order:

1. the current explicit task and preservation contract;
2. Julia language semantics and established public dependency interfaces;
3. the normative laws in this playbook;
4. a current repository-specific profile that only instantiates or tightens these laws;
5. the companion ownership and Template Method playbooks;
6. current maintained public documentation;
7. current tests that protect supported behavior;
8. current implementation details;
9. old plans, prompts, reports, branches, snapshots, generated guides, examples, and remembered code.

A lower-ranked source may provide evidence. It may not silently overturn a higher-ranked rule.

### 1.2 Examples never outrank laws

Examples, seeds, skeletons, and reference implementations are not normative APIs.

When an example conflicts with a general law:

- the law wins;
- the example is corrected, removed, or classified as an anti-example;
- the conflict is not resolved by inventing a compatibility wrapper around the mistake.

A seed that contains an abstract type, context, hook, manager, `supports` predicate, `finish` stage, or adapter does not authorize those constructs in another subsystem. Every participant must independently pass abstraction admission.

### 1.3 Repository code is evidence, not precedent

The following statements are not warrants:

- “the repository already does this”;
- “several files use it”;
- “the tests expect it”;
- “it is documented”;
- “an earlier refactor established it”;
- “it is generic”;
- “it is convenient”;
- “it may be useful later.”

Reach proves only that a decision spread. Cancer also has excellent change propagation.

---

## 2. Governing law

### 2.1 Native-First Semantic Economy

> **Use Core, Base, the standard library, dependency-owned public interfaces, constructors, and already admitted repository generics before introducing a new project-owned generic function, type, wrapper, trait, stage, registry, context, alias, module, or compatibility path.**

The compact law is:

> **Every new name must add semantic information.**

A proposed abstraction has zero semantic delta when replacing it with the underlying operation changes none of the following:

- domain meaning;
- invariant;
- dispatch behavior;
- ownership;
- result contract;
- error contract;
- lifecycle;
- external boundary;
- supported compatibility contract;
- measured performance behavior.

A zero-semantic-delta abstraction is forbidden. It is not documentation. It is another fact every developer and agent must carry indefinitely.

### 2.2 Directness is the default

When no admitted abstraction owns the operation, write the operation directly in the code that owns it.

Direct code is preferred when the operation:

- has one caller;
- is short and locally understandable;
- does not vary by dispatch;
- does not establish a reusable invariant;
- does not isolate an external boundary;
- does not own a coherent algorithm;
- is part of a visible orchestration sequence.

A comment may explain local intent without creating another callable authority.

### 2.3 Methods and generic names are different architectural costs

Julia code may become more extensible by adding methods to an existing generic without increasing the number of semantic authorities.

```text
more methods on one admitted generic: often good
more one-method generic functions: usually bad
```

Count new generic names separately from new methods.

A cleanup may replace one branch-heavy method with several methods of an existing generic and still reduce architecture. Extracting ten private one-method functions from one coherent action increases architecture even when each function is only three lines and the cyclomatic-complexity dashboard begins purring contentedly.

### 2.4 Refactor monotonicity

For cleanup, convergence, migration, ownership repair, and behavior-preserving refactors:

> **The number of semantic authorities and execution paths must not increase unless the task explicitly introduces a new domain capability, external integration, or supported compatibility contract.**

The default diff budget is:

```text
new project-owned generic names:       0
new abstract types:                    0
new wrapper/result types:              0
new modules or submodules:             0
new registries or selector maps:       0
new compatibility paths:               0
new orchestration paths:               0
new external-workaround suppressions:  0
```

Method count, test count, and explicit owner-local statements may increase when they replace branches, hidden coupling, or duplicated authority.

### 2.5 Abstractions compress semantics, not syntax

Textual repetition is not sufficient evidence of shared meaning.

Two code fragments belong behind one abstraction only when they represent the same knowledge, have the same owner, and should change together for the same reason.

Similar syntax with different owners or reasons for change should remain separate. This is the useful interpretation of DRY: eliminate duplicated knowledge, not every repeated token sequence produced by a formatter.

---

## 3. Terms

### 3.1 Semantic authority

A semantic authority is a named construct that claims ownership of meaning or behavior.

Examples include:

- a generic function;
- an abstract type;
- a concrete policy or descriptor type;
- a wrapper result;
- a registry;
- a module or submodule;
- a public alias or deprecation path;
- an orchestration path;
- a selector, unit, metadata, or serialization grammar.

A method added to an existing generic normally extends an authority. It does not create a second one.

### 3.2 Semantic delta

The semantic delta of a construct is the information it adds beyond:

- its argument and result types;
- its owner;
- its callee;
- the surrounding action;
- an existing native or repository interface.

A construct with zero semantic delta is rejected.

### 3.3 Module-level helper

A module-level helper is a project-owned function that supports another operation without owning a first-class domain action, invariant, algorithm, lifecycle, external boundary, or extension contract.

It is presumptively defective when it:

- has one method and one caller;
- forwards arguments unchanged;
- reads or repacks fields;
- wraps `merge`, `collect`, `convert`, `promote`, `eltype`, `length`, `size`, `first`, `last`, or another established operation;
- compensates for two package-owned interfaces that disagree;
- hides part of a public choreography;
- exists only to shorten the caller;
- is imported or extended outside its owner despite an underscore prefix.

### 3.4 Local implementation function

A nested function or closure used only inside one coherent algorithm is not a repository-wide semantic authority.

It is legitimate when it:

- captures algorithm-local state;
- names a repeated low-level operation inside one kernel;
- improves readability or performance locally;
- is not imported, extended, exported, or tested as an independent protocol.

Do not promote it to module scope in anticipation of imaginary reuse.

### 3.5 Kernel

A kernel owns coherent numerical, physical, geometric, parsing, transformation, or encoding logic.

A kernel may:

- have one caller;
- be long;
- contain loops and data-dependent branches;
- allocate or reuse buffers;
- contain local functions;
- deserve independent tests, profiling, or mathematical review.

A kernel is not a tiny helper merely because it is private or has one caller. Its warrant is coherent algorithmic meaning.

### 3.6 Shim

A shim bridges incompatible interfaces.

- An **internal shim** bridges two package-owned contracts. Internal shims are forbidden; repair the owners and perform one finite cutover.
- An **external shim** compensates for a contract outside repository control. It may be admitted only when narrow, isolated, tested, version- or capability-scoped, and tied to a removal condition.
- A **compatibility layer** preserves an identified released API, persisted format, or downstream consumer. It is not justified by hypothetical users.

### 3.7 Adapter

An adapter translates between one repository-owned semantic contract and an external contract.

An adapter may own representation translation and I/O mechanics. It may not rediscover domain policy that belongs to the core package.

### 3.8 First-class action

A first-class action is a stable operation with:

- one owner;
- a supported input domain;
- a result contract;
- an obvious public entry point;
- behavior important enough to document and test independently.

Only admitted first-class actions are candidates for a dispatch-driven Template Method.

---

## 4. Abstraction admission procedure

Apply the following gates in order. A failed gate ends the review.

### Gate 1: Is the behavior required now?

Reject a proposed abstraction whose only motivation is:

- symmetry;
- future extensibility without a concrete extension;
- shortening a function;
- satisfying an arbitrary method-length or complexity threshold;
- avoiding direct language syntax;
- creating a home for code with no owner;
- preserving an unreleased name;
- matching a diagram, seed, or design-pattern checklist.

Start from required behavior, not from a noun ending in `Manager`.

### Gate 2: Does an existing authority already express the exact meaning?

Search in this order:

```text
Core and Base
→ standard library
→ dependency-owned public interface
→ existing admitted repository generic
→ direct owner-local code
→ warranted new abstraction
```

Stop at the first exact semantic match.

Do not overload a native operation with unrelated meaning merely to avoid a project-owned name. Native precedence requires semantic equivalence, not cosplay.

### Gate 3: Would direct owner-local code be clearer?

Prefer direct code when the operation has no independent meaning outside the caller.

A new name is not automatically clearer. It may force the reader to leave the action, find another file, reconstruct a one-line body, and return with less information than before. This is not abstraction. It is a scavenger hunt.

### Gate 4: Can the behavior be another method of an admitted generic?

When the operation already has one meaning and behavior varies by type, add a method.

Do not create source-specific variants such as:

```text
scale_from_file
scale_from_result
scale_from_definition
```

when all calls mean the same operation and the source types provide the dispatch distinction.

### Gate 5: Does the new authority have an actual warrant?

A new authority must satisfy at least one warrant in Section 5. “Might be reusable” is not a warrant.

### Gate 6: Is there one honest owner?

The proposed construct must have one owner that controls:

- its meaning;
- admitted inputs;
- result or invariant;
- extension policy;
- tests.

A function created because two siblings both need “something like this” has no owner until the shared semantic contract is stated precisely.

### Gate 7: Does it reduce rather than multiply authority?

Reject a construct that creates:

- a second way to perform an existing action;
- a second type-query vocabulary;
- a second selector or unit map;
- a registry mirroring dispatch;
- a wrapper around an already owned result;
- a parallel old/new execution path;
- a second error or validation grammar.

### Gate 8: Is current evidence sufficient?

The warrant must be supported by current callers, current extension methods, a current boundary, a measured performance need, or a named compatibility obligation.

Historical snapshots and speculative future consumers do not pass this gate.

### Gate 9: Can the contract be tested directly?

An admitted abstraction must have tests for the semantic fact it claims to own.

Tests that merely execute a wrapper do not prove the wrapper is meaningful.

---

## 5. Valid warrants

A warrant is necessary but not sufficient. Native precedence, ownership, semantic delta, and current evidence still apply.

### 5.1 Domain-action warrant

The construct names a stable operation in the problem domain and owns one result contract.

Examples:

```julia
project(definition, result_space)
validate(entry)
solve(problem, algorithm)
kron_reduce(matrix, retained)
```

The name must survive changes in implementation. If it merely restates the current callee, it fails.

### 5.2 Invariant warrant

The construct establishes or verifies a nontrivial invariant at more than one owned boundary, or is itself the explicit boundary of one first-class action.

Examples include:

- validating that a graph remains acyclic before construction;
- verifying that a result collection has one concrete element grammar;
- enforcing dimensional compatibility before unit conversion.

A one-line predicate with one caller should normally remain inline.

### 5.3 Dispatch-contract warrant

A generic is an actual extension seam when:

- multiple current concrete types require distinct behavior;
- the behavior has one stable meaning;
- adding a method is the documented extension path;
- the generic is owned and tested as a protocol.

One method plus “others may be added later” is not evidence.

### 5.4 Algorithm warrant

The construct owns coherent mathematics or an algorithm deserving independent review, testing, profiling, or reuse.

Examples:

```text
kron_reduce
hungarian_assignment
modal_transform
parse_expression_without_eval
```

A meaningful algorithm may have one caller. Reuse count is not the decisive criterion.

### 5.5 Lifecycle warrant

The construct owns real state or resources across several operations.

Examples:

- a preallocated numerical workspace;
- a transaction with commit/rollback semantics;
- a UI runtime context;
- an external process session;
- a file or database lifecycle.

A `Context` that merely bundles arguments to shorten signatures fails.

### 5.6 External-boundary warrant

The construct isolates a package, protocol, file format, operating system, external solver, vendor API, or UI backend outside repository control.

The adapter or shim belongs to the integration owner and may not absorb core domain policy.

### 5.7 Compatibility warrant

The construct preserves one identified supported contract:

- a released documented API;
- a versioned persisted format;
- a known downstream package;
- an explicit support commitment;
- an approved migration window.

The record must name the consumer or format and state a removal condition when temporary.

### 5.8 Measured-performance warrant

The construct establishes a verified function barrier, specialization point, preallocation boundary, or allocation reduction.

Evidence must come from:

- inference inspection;
- allocation measurement;
- a benchmark;
- a documented compiler limitation.

“Julia probably likes smaller functions” is folklore, not data.

### 5.9 Abstraction warrant record

Every new semantic authority records:

```text
Name:
Owner:
Kind: generic | type | module | wrapper | registry | compatibility path | other
Required behavior:
Native alternatives checked:
Dependency interfaces checked:
Existing repository alternatives checked:
Semantic delta:
Current callers:
Current method family:
Invariant or result contract:
External boundary, if any:
Compatibility evidence, if any:
Performance evidence, if any:
Why direct owner code is insufficient:
Tests:
Removal condition, if temporary:
```

An empty required field is a failed admission review, not a minor documentation omission.

---

## 6. Tiny-helper discipline

### 6.1 Default rule

For cleanup and convergence work:

> **The budget for new module-level private generic names is zero.**

A deviation requires an approved warrant before implementation.

For feature work, new names remain presumptively unapproved until they pass the same admission procedure.

### 6.2 Small methods are encouraged

The policy does not ban short methods. Julia interfaces are often implemented through concise methods.

```julia
Base.eltype(::Type{ResultBatch{T}}) where {T} = T
Base.length(batch::ResultBatch) = length(batch.values)
Base.getindex(batch::ResultBatch, i::Int) = batch.values[i]
```

These methods complete one existing semantic authority.

The following create redundant vocabulary and are rejected:

```julia
_result_type(batch) = eltype(batch)
_result_count(batch) = length(batch)
_result_at(batch, i) = batch[i]
```

### 6.3 One caller is a signal, not an automatic verdict

A one-caller function is admitted when it owns a coherent algorithm, invariant, lifecycle, or external boundary.

A one-caller function is rejected when it merely:

- forwards;
- repacks;
- reads a field;
- merges defaults;
- renames a native call;
- hides a few statements from an orchestrator.

### 6.4 Local functions remain local

```julia
function normalize_rows!(A)
    rownorm(i) = sqrt(sum(abs2, @view A[i, :]))

    for i in axes(A, 1)
        n = rownorm(i)
        iszero(n) || (@view(A[i, :]) ./= n)
    end
    return A
end
```

`rownorm` is an implementation detail of one kernel. Promoting it to `_row_norm` at module scope would add architecture without adding meaning.

### 6.5 Extraction test

Before extracting a module-level function, answer:

1. Does the name express a domain action, invariant, algorithm, lifecycle, or external boundary?
2. Does behavior vary by dispatch now?
3. Do multiple current callers require the same semantics and change for the same reason?
4. Would direct Julia syntax be clearer at each call site?
5. Does extraction hide the public action sequence?
6. Is the function compensating for a malformed package-owned contract?
7. Is the name merely a comment converted into a callable symbol?

A negative answer to question 1 combined with a positive answer to any of questions 4 through 7 means do not extract.

### 6.6 Underscore prefixes grant no architectural exemption

A private name is still a generic function and still increases repository vocabulary.

```julia
_normalize_resolved_normalized_input(...)
```

is not cheaper because it begins with an underscore. It may be worse because the name advertises that nobody could state what it owns.

### 6.7 Cross-owner private use is forbidden

A sibling module or package extension may not import, call, or extend an underscore-prefixed method from another owner.

When a private method becomes a real cross-owner contract:

- give it a semantic owner-visible name;
- document its admitted domain;
- test the extension seam;
- remove the private alias.

When it does not pass admission, remove the dependency instead.

### 6.8 File and module rule

Runtime source must not introduce catch-all artifacts named:

```text
helpers.jl
utils.jl
common.jl
shared.jl
misc.jl
Helpers
Utils
Common
Commons
Shared
Misc
```

A coherent shared contract must be named after what it owns, such as `Units`, `Observables`, `Validation`, or `Serialization`.

A file named after a concrete algorithm or protocol is allowed only after that algorithm or protocol passes admission.

---

## 7. Julia-native baseline

### 7.1 Multiple dispatch is the default variation mechanism

When one operation has one meaning but behavior varies by types, define methods of one generic.

Avoid source-encoded names and central switches:

```julia
# Rejected
scale_from_file(x) = ...
scale_from_result(x) = ...

# Preferred
scale(x::InputFile) = ...
scale(x::ComputedResult) = ...
```

Use symbols and strings at user, configuration, or serialization boundaries. Normalize them once into typed values before the extensible core.

### 7.2 Collections use Base interfaces

A finite collection should implement the relevant standard interface:

- `iterate`;
- `length`;
- `size` when shape is meaningful;
- `eltype`;
- `getindex` when indexing is part of the contract;
- `firstindex` and `lastindex` when indexed.

Then use Base-provided behavior such as:

- `first`;
- `last`;
- `only`;
- `collect`;
- `map`;
- `zip`;
- comprehensions.

Do not create parallel accessors that restate those facts.

### 7.3 Constructors own construction invariants

Use outer constructors to:

- normalize user-facing input;
- promote values;
- validate invariants;
- choose concrete owned types;
- delegate to a tight constructor.

Do not add a generic “construction manager” merely to avoid putting construction policy with the owned type.

### 7.4 Native promotion and conversion take precedence

Use:

- `promote` for values that must participate in one operation;
- `promote_type` when a concrete common element type is required;
- constructors to establish owned-object invariants;
- `convert` for a meaningful representation-preserving conversion;
- `promote_rule` when the owner of a numeric type must define combination behavior.

Example:

```julia
struct Interval{T}
    lo::T
    hi::T
end

function Interval(lo, hi)
    lo′, hi′ = promote(lo, hi)
    lo′ <= hi′ || throw(ArgumentError("lo must not exceed hi"))
    return Interval{typeof(lo′)}(lo′, hi′)
end
```

Reject repository-wide mechanisms that recursively inspect arbitrary structs, discover embedded scalar categories, and coerce arrays, tuples, NamedTuples, and unrelated objects through one god-function.

### 7.5 Lossy transformation is not conversion

Dropping uncertainty, discarding an imaginary component, changing basis, taking a magnitude, clipping, or projecting to a representative is a domain transformation.

It must be named and owned by the action that requests it.

Do not hide it behind `convert`, `coerce`, `normalize`, or a generic scalar-type resolver.

```julia
# Explicit domain choice
magnitudes = abs.(spectrum)
real_component = real.(spectrum)
```

### 7.6 Human display uses `show` and `showerror`

Use `Base.show` for object display and `Base.showerror` for exception rendering when those native protocols match the requirement.

```julia
function Base.show(io::IO, summary::RunSummary)
    print(io, "RunSummary(", summary.completed, "/", summary.total, ")")
end
```

Do not create `_pretty_summary`, `display_text`, and `describe_for_repl` merely to reconstruct Julia’s display protocol.

A separate formatter is legitimate when it produces a real external format rather than human display.

### 7.7 Mutation names must tell the truth

A method ending in `!` mutates an advertised argument on every successful supported path, subject to normal Julia conventions for RNG and I/O.

A function that sometimes returns a replacement while leaving the original untouched is not a truthful mutating API. Use a non-mutating name or separate the operations explicitly.

### 7.8 Protocol support is not discovered by exceptions

Do not select package-owned behavior through:

- `catch MethodError` retry chains;
- `applicable` probes that mirror dispatch;
- repeated arity guessing;
- `hasproperty` cascades;
- dictionary, NamedTuple, field, indexing, and exception fallbacks for the same concept.

Define one contract and dispatch on it.

Dynamic probing may be justified at an uncontrolled external boundary, but it belongs in the adapter and must not leak into core semantics.

### 7.9 Traits are exceptional, not decorative

Use a trait only when behavior depends on a stable orthogonal property that cannot be represented cleanly by the existing types.

Reject a trait that:

- has one value for every current subtype;
- mirrors a type hierarchy;
- exists to avoid two ordinary methods;
- becomes a second registry of the same behavior.

### 7.10 `Val` is a dispatch tool, not a symbol laundering machine

`Val` is appropriate for small bounded compile-time distinctions already present at a boundary.

Do not convert arbitrary runtime symbols into `Val` throughout hot paths or use `Val` to make a symbol switchboard appear type-driven.

### 7.11 Runtime `eval` is not an input grammar

Do not use `eval` or `@eval` in runtime source to interpret user input, discover internal behavior, mutate package modules, or register owned semantics.

Approved code generation or an isolated external workaround requires explicit ownership and tests.

---
## 8. Shim, adapter, and compatibility law

### 8.1 Internal shims are forbidden

When two package-owned modules disagree:

1. identify the real owner of the concept;
2. select one contract;
3. migrate all current consumers in one finite campaign;
4. update tests and maintained documentation;
5. delete the old contract;
6. delete the bridge.

Do not add:

- old-to-new forwarding methods;
- new-to-old forwarding methods;
- internal compatibility modules;
- ignored keywords;
- field aliases;
- wrappers preserving both representations;
- arity-retry chains;
- structural-probing fallbacks;
- “temporary” `_shim` functions with no deletion commit.

An internal shim does not resolve disagreement. It preserves both disagreeing sides and adds a third contract that future developers will be afraid to remove.

### 8.2 External shims require strict evidence

An external shim is admitted only when the incompatible side is outside repository control and ordinary use of the external public API is insufficient.

The shim record is mandatory:

```text
External package or system:
Affected version or capability range:
Upstream issue, documented contract, or reproducible defect:
Why ordinary extension or adaptation is insufficient:
Exact behavior overridden or repaired:
Owning integration:
Integration tests:
Failure behavior outside the affected range:
Removal condition:
Review date:
```

A valid external shim is:

- narrow;
- one-directional;
- isolated in the integration owner;
- version- or capability-gated;
- covered by a real integration test;
- removable without changing domain policy.

### 8.3 Compatibility is a contract, not a superstition

A compatibility layer exists only for an identified supported consumer or format.

Valid evidence includes:

- a released documented API;
- a versioned persisted artifact;
- a known downstream package;
- a contractual integration;
- an approved deprecation window.

Invalid evidence includes:

- “someone may use it”;
- “the old name was in a branch”;
- “there is a test”;
- “removing it feels risky.”

For unreleased or explicitly breaking early-stage work, migrate and delete. Do not build a museum exhibit around every renamed function.

### 8.4 Compatibility paths are public and finite

A legitimate compatibility path must be:

- documented as compatibility, not disguised as an internal helper;
- one-directional toward the current contract;
- free of new domain behavior;
- tested against the supported old contract;
- associated with a removal version or condition.

Do not hide compatibility behind an underscore. A supported compatibility contract is public by definition.

### 8.5 Adapters own translation, not domain policy

An adapter may:

- convert an owned result into an external library object;
- encode an owned table into a file format;
- translate external exceptions into owned boundary errors;
- activate or call an external backend.

An adapter may not:

- rediscover scientific quantities;
- choose domain semantics;
- infer units from field names;
- duplicate validation policy;
- create another selector grammar;
- reconstruct an action already owned by the core package.

The core owner produces a complete semantic payload. The adapter performs the external translation. There is no need for a tiny parliament between them.

---

## 9. Wrapper, context, registry, and layer discipline

### 9.1 Exact forwarding wrappers are forbidden

```julia
# Rejected
_make_report(args...; kwargs...) = make_report(args...; kwargs...)
```

Call `make_report` directly.

A wrapper is admitted only when it deliberately changes a real contract, such as:

- boundary normalization;
- invariant enforcement;
- public API semantics distinct from an internal kernel;
- lifecycle or transaction behavior;
- external exception translation;
- supported compatibility.

Changing the function name while preserving arguments, result, errors, and side effects adds no semantics.

### 9.2 Field wrappers require a semantic contract

```julia
# Rejected: private spelling expansion
_get_name(x) = x.name
```

Use `x.name` inside the owner.

An exported accessor can be legitimate when it defines stable semantics across representations:

```julia
coordinates(path::Polyline) = path.points
coordinates(mesh::SurfaceMesh) = mesh.vertices
```

Here `coordinates` is not merely a field alias. It is a public semantic read shared by different owned representations.

### 9.3 One-field wrappers are presumptively defective

A wrapper type that stores one existing value and delegates all behavior back to it requires a concrete invariant, dispatch distinction, lifecycle, ownership transfer, or boundary role.

Reject wrappers created only to:

- make types “more explicit”;
- reserve room for future metadata;
- avoid passing a native collection;
- give an internal function a unique dispatch signature;
- hide a dependency without changing the contract.

### 9.4 Contexts and workspaces must own state

A valid workspace or context owns state that crosses several operations:

```text
preallocated buffers
transaction state
backend handles
observer registrations
external session state
resolved layout state
```

A context that only collects arguments into a struct to shorten method signatures is an argument bag, not an architecture concept.

### 9.5 Registries must not mirror dispatch

Do not maintain both:

- a dictionary from symbols to types or functions; and
- a method family selecting the same bounded behavior.

Choose one authority.

Registries are justified for genuinely runtime-extensible external plugins, user-installed providers, or data-driven configuration whose membership cannot be known through normal package loading. They are not justified because an agent finds a dictionary easier to generate than methods.

### 9.6 Different layer, different abstraction

A new layer must expose a different and simpler contract than the layer beneath it.

Reject a layer that repeats the same operation with:

- the same arguments;
- the same result;
- the same errors;
- the same side effects;
- another name.

Pass-through methods are a red flag. Repeated abstraction at adjacent layers is not separation of concerns. It is concern duplication.

### 9.7 Manager, provider, factory, service, and handler names require proof

These names are not banned because of spelling. They are flagged because they often conceal the absence of an owned concept.

A proposed `Manager`, `Provider`, `Factory`, `Service`, or `Handler` must state:

- what resource, lifecycle, or policy it owns;
- why constructors, dispatch, or an existing owner cannot express it;
- which current implementations require the protocol;
- what result or invariant belongs to it.

Without those answers, use the actual domain noun or direct code.

### 9.8 Error-handler hierarchies are not the default

Julia exceptions and `showerror` are the baseline.

A handler hierarchy is admitted only when multiple current policies consume one structured issue contract, for example:

- immediate throwing;
- issue accumulation;
- UI presentation;
- report generation.

A future possibility of collecting errors does not justify `AbstractErrorHandler`, `ThrowingHandler`, `CollectingHandler`, and a dozen forwarding methods today.

---

## 10. Composition with Dispatch-Driven Template Method

### 10.1 Admission comes first

The Template Method pattern structures a first-class action after the action and its variable stages have passed this playbook.

Do not create a Template Method merely because an operation has several sequential statements.

### 10.2 The choreography stays visible

A valid orchestrator shows the fixed high-level sequence in one owner.

```julia
function publish(definition, source)
    request = select(definition, source)
    payload = materialize(definition, request)
    return Publication(payload, definition.destination)
end
```

Do not hide the entire sequence behind `_run_pipeline`, a callable manager, a chain of closures, or a context object.

### 10.3 Only genuinely variable stages become generic hooks

A stage becomes a generic hook only when current admitted types require distinct implementations of the same semantic step.

Fixed statements remain direct statements.

```julia
function process(definition, source)
    selected = select(definition, source)        # real dispatch variation
    transformed = transform(definition, selected) # real dispatch variation
    return Output(transformed)                   # fixed assembly, keep direct
end
```

Do not introduce `finish(definition, transformed)` solely to make the stage diagram symmetrical.

### 10.4 Required hooks have no silent broad fallback

A required hook must fail at dispatch when absent.

Reject defaults such as:

```julia
prepare(::Any, x) = x
kind(::Type) = :unknown
result_type(::Type) = Any
supports(::Type, ::Type) = false
```

when they allow a missing implementation to continue into delayed nonsense.

### 10.5 Optional hooks require real optional behavior

An identity or no-op hook is valid only when:

- the stage semantically belongs to the action;
- at least one current admitted implementation specializes it nontrivially;
- the default represents legitimate non-applicability.

Do not add optional hooks as placeholders for possible future customization.

### 10.6 Entitlement must not mirror method availability

Dispatch already determines whether a method exists.

A separate `supports`, `entitled`, or `can_process` generic is rejected when it merely repeats method availability.

An entitlement stage is legitimate when it validates runtime facts that dispatch cannot express before side effects, such as:

- retained data availability;
- dimensional compatibility;
- external resource capability;
- shape or basis compatibility.

### 10.7 Definitions declare; they do not execute

A definition may hold passive policy and user choices. It does not:

- run the action;
- discover handlers;
- decode a generic mode registry;
- become a mutable runtime context;
- return a shadow result wrapper.

Behavior is expressed by methods dispatched on the concrete definition type when genuine variation exists.

### 10.8 Seeds are not shopping lists

Do not copy a complete seed containing:

- abstract definitions;
- abstract inputs;
- contexts;
- `supports`;
- normalize/check/prepare/postprocess stages;
- result wrappers;
- handlers;
- registries;

unless every participant independently passes abstraction admission.

---

## 11. Composition with ownership-centered layout

### 11.1 Owner before helper

Every surviving concept must have one owner. A shared dumping module is not an owner.

A directory or file is created only after the concept passes admission.

### 11.2 Place methods by the reason they change

- Base protocol methods live beside the owned type in `base.jl`, `show.jl`, `iteration.jl`, `indexing.jl`, or another precise protocol file.
- A first-class action lives in a file named after the action.
- A coherent algorithm lives in a file named after the algorithm.
- Optional dependency behavior lives in a package extension.
- Definition-specific methods remain near the definition they explain.

### 11.3 No helper-shaped scaffolding

Do not create empty or generic files by ritual:

```text
helpers.jl
utils.jl
common.jl
managers.jl
providers.jl
services.jl
implementations.jl
```

The file tree should reveal domain owners and protocols, not the agent’s preferred bag of design-pattern nouns.

### 11.4 Directory before submodule

Use a directory for navigation before creating a Julia submodule.

A submodule requires a real namespace, dependency, interface, collision, or lifecycle distinction. It is not a larger folder with `module` written at the top.

### 11.5 Cross-owner extension seams are explicit

A method imported or extended by another owner is not private.

Promote a legitimate seam to a documented owner-visible generic. Remove an illegitimate seam. Do not leave it underscore-prefixed and call the resulting dependency “internal.”

---

## 12. Concrete example catalogue

These examples are synthetic. They illustrate the rules and do not declare current repository APIs.

### 12.1 Collection semantics

#### Rejected

```julia
struct ResultBatch{T}
    values::Vector{T}
end

_result_values(batch) = batch.values
_result_type(batch) = eltype(batch.values)
_result_count(batch) = length(batch.values)
_single_result(batch) = only(batch.values)
```

#### Preferred

```julia
struct ResultBatch{T}
    values::Vector{T}
end

Base.IteratorSize(::Type{<:ResultBatch}) = Base.HasShape{1}()
Base.IteratorEltype(::Type{<:ResultBatch}) = Base.HasEltype()
Base.eltype(::Type{ResultBatch{T}}) where {T} = T
Base.iterate(batch::ResultBatch, state...) = iterate(batch.values, state...)
Base.length(batch::ResultBatch) = length(batch.values)
Base.size(batch::ResultBatch) = (length(batch),)
Base.getindex(batch::ResultBatch, i::Int) = batch.values[i]
Base.firstindex(batch::ResultBatch) = firstindex(batch.values)
Base.lastindex(batch::ResultBatch) = lastindex(batch.values)
```

Base now supplies `first`, `last`, `only`, `collect`, `map`, and `zip` behavior through one standard authority.

### 12.2 Native promotion

#### Rejected

```julia
resolve_scalar_type(args...) = # recursive scan of every nested value
coerce_everything(x, ::Type{T}) where {T} = # recursive reconstruction
```

#### Preferred

```julia
struct PairValue{T}
    left::T
    right::T
end

function PairValue(left, right)
    left′, right′ = promote(left, right)
    return PairValue{typeof(left′)}(left′, right′)
end
```

Owned constructors establish the object. Native promotion establishes the common scalar relation.

### 12.3 Explicit lossy transformation

#### Rejected

```julia
coerce_to_real(z::Complex) = real(z)
coerce_to_real(x::Measurement) = value(x)
```

These operations discard information and are not generic coercion.

#### Preferred

```julia
real_curve = real.(complex_curve)
nominal_curve = Measurements.value.(uncertain_curve)
```

The calling action states the requested projection explicitly.

### 12.4 Forwarding wrapper

#### Rejected

```julia
_render(args...; kwargs...) = render(args...; kwargs...)
```

#### Preferred

```julia
render(args...; kwargs...)
```

There is no semantic difference to preserve.

### 12.5 Semantic accessor

#### Rejected

```julia
_get_points(path) = path.points
```

#### Potentially admitted

```julia
coordinates(path::Polyline) = path.points
coordinates(mesh::SurfaceMesh) = mesh.vertices
```

The second form can define one public semantic read across representations. Its warrant depends on real consumers and ownership, not on the attractiveness of the name.

### 12.6 Algorithm with one caller

```julia
function kron_reduce(Y, retained)
    # coherent numerical algorithm
end
```

This may be valid with one caller because it owns identifiable mathematics, can be reviewed independently, and is not a renamed expression.

### 12.7 Internal mismatch

#### Rejected

```julia
_to_new_payload(old::OwnedPayload) = NewPayload(old.a, old.b)
```

when both contracts are package-owned and the bridge exists only to keep both alive.

#### Preferred

Choose one payload contract, migrate every consumer, and remove the other representation in the same finite campaign.

### 12.8 External adapter

```julia
module PackageCSVExt

import PackageName: encode
import CSV

function encode(::CSVFormat, table::OwnedTable)
    return CSV.write(IOBuffer(), table.rows)
end

end
```

This is legitimate only if `OwnedTable` already contains the table semantics. The extension must not rediscover domain selection or units.

### 12.9 Display

#### Rejected

```julia
_pretty_run(run) = "Run($(run.completed)/$(run.total))"
```

when the only consumer is REPL or log display.

#### Preferred

```julia
function Base.show(io::IO, run::RunSummary)
    print(io, "RunSummary(", run.completed, "/", run.total, ")")
end
```

### 12.10 Callback contract

#### Rejected

```julia
function invoke_callback(f, ctx, item)
    try
        return f(ctx, item)
    catch err
        err isa MethodError || rethrow()
    end
    try
        return f(ctx)
    catch err
        err isa MethodError || rethrow()
    end
    return f()
end
```

#### Preferred

Define one callback signature, or adapt external callbacks once at the boundary into one owned callable object.

### 12.11 Decorative hook

#### Rejected

```julia
finish(::AbstractDefinition, value) = value
```

when no current implementation specializes `finish`.

#### Preferred

Return `value` directly in the orchestrator. Add a hook later only when a current semantic variation exists.

### 12.12 Context as argument bag

#### Rejected

```julia
struct ProcessingContext
    source
    definition
    options
end
```

when it has no invariant or lifecycle and merely replaces three arguments.

#### Potentially admitted

```julia
mutable struct SolverWorkspace{T,M}
    matrix::M
    rhs::Vector{T}
    factorization
end
```

when it owns reusable buffers and a measured numerical lifecycle.

### 12.13 Compatibility alias

#### Rejected

```julia
old_name(args...; kwargs...) = new_name(args...; kwargs...)
```

without release or consumer evidence.

#### Admitted only under contract

A documented deprecation from a released API to a current API, with tests and a stated removal version.

---
## 13. Mechanical guardrails

The purpose of automation is not to prove that code is meaningful. No AST parser can inspect a function and discover enlightenment. The purpose is to reject mechanically obvious violations and force explicit review for suspicious constructs.

Use four complementary views:

1. AST inspection;
2. symbol and method inventory;
3. owner-aware call-graph analysis;
4. diff-scoped semantic-authority budgets.

### 13.1 Hard-failure rules

| ID | Detection | Failure |
|---|---|---|
| `NSE001` | A top-level method body is one call to another package-owned function and forwards the same positional and keyword arguments unchanged. | Exact forwarding wrapper. |
| `NSE002` | A module or extension imports, qualifies, calls, or extends an underscore-prefixed name from another owner. | Private cross-owner protocol. |
| `NSE003` | Runtime source introduces a catch-all file or module named `Utils`, `Helpers`, `Common`, `Commons`, `Shared`, `Misc`, or equivalent. | Ownerless dumping artifact. |
| `NSE004` | A private project-owned function directly returns a native fact such as `eltype`, `length`, `size`, `first`, `last`, `only`, `keys`, or `values`, with no changed contract. | Native duplicate query. |
| `NSE005` | Package-owned behavior is selected through `catch MethodError`, arity retries, or `applicable` rather than one internal protocol. | Exception-based protocol discovery. |
| `NSE006` | Runtime source uses `eval` or `@eval` for user grammar, owned dispatch registration, or internal module mutation outside an approved boundary. | Dynamic owned grammar. |
| `NSE007` | A new alias, ignored keyword, fallback constructor, old-name wrapper, or deprecation lacks named compatibility evidence. | Compatibility theater. |
| `NSE008` | A required protocol fallback returns `Any`, `:unknown`, `nothing`, `false`, or `()` and lets execution continue. | Hidden interface defect. |
| `NSE009` | A fixed package-owned concept is represented by both a symbol registry/switch and a dispatch method family. | Duplicate semantic authority. |
| `NSE010` | A new module-level helper hides a contiguous portion of a public action while being called only by that action and having no warrant. | Hidden choreography. |
| `NSE011` | A package-owned semantic path probes fields, dictionaries, NamedTuples, indexing, and exceptions to support several owned representations of the same concept. | Internal compatibility shim by structural probing. |
| `NSE012` | A new repository-wide scalar/type resolver or recursive coercion engine duplicates native promotion, constructors, and `convert`. | Reimplemented language semantics. |
| `NSE013` | A method ending in `!` has a successful supported path that mutates none of its advertised arguments and returns a replacement instead. | Dishonest mutation API. |
| `NSE014` | A compatibility or shim suppression has no external system, affected range, test, owner, and removal condition. | Unbounded suppression. |
| `NSE015` | A cleanup/refactor diff introduces a new semantic authority without an approved warrant record. | Refactor monotonicity violation. |

Hard-failure rules may allow a narrowly scoped suppression only where this playbook explicitly permits one. Internal shims, exact forwarders, private cross-owner protocols, and catch-all modules are not suppressible.

### 13.2 Mandatory-review candidates

The following patterns are not automatically defects, but the author bears the burden of proof:

- a new private generic with one method;
- a new private generic with one production caller;
- a function with no substantive body beyond field access, tuple construction, `merge`, `collect`, `convert`, or a native query;
- a new abstract type with one internal subtype;
- a one-field wrapper delegating nearly all behavior;
- a new `Manager`, `Provider`, `Factory`, `Service`, `Handler`, `Context`, `Adapter`, or `Registry`;
- a generic hook with no non-default specialization;
- an identity or no-op hook added for symmetry;
- a new trait that mirrors existing types;
- a new symbol dictionary whose keys correspond to concrete types or methods;
- a new module or submodule created only to hide private names;
- a new “normalization” step between two package-owned typed representations;
- a helper extracted solely because a function exceeded a line-count or complexity threshold;
- a local function promoted to module scope without a second semantic owner;
- a new compatibility path during pre-release or explicitly breaking work;
- a new layer exposing the same arguments and result as the layer below.

### 13.3 AST forwarder detection

An exact-forwarder detector should identify a method where:

1. the body contains one optional `return` and one call;
2. the callee is another package-owned generic;
3. every positional argument is forwarded once in the same order;
4. varargs and keywords are forwarded unchanged;
5. no validation, conversion, transformation, error translation, or lifecycle behavior occurs.

The detector should exclude:

- constructors that change the public contract;
- deprecations with approved compatibility evidence;
- external-boundary adapters;
- methods that deliberately select a different dispatch axis or enforce an invariant.

### 13.4 Symbol inventory

For every baseline and changed revision, collect:

- generic-function names;
- method counts per generic;
- abstract and concrete types;
- modules and submodules;
- exports and public names;
- registries and large symbol maps;
- aliases and deprecations;
- runtime files;
- first-class entry points.

Report separately:

```text
new methods on existing generics
new generic names
new types
new modules
new exports
new compatibility paths
```

A single combined “functions added” number hides the distinction this policy exists to enforce.

### 13.5 Owner-aware call graph

The call graph should map each source file to its owner and flag:

- cross-owner calls to underscore-prefixed names;
- wrappers whose only purpose is to cross an owner boundary;
- several consumers independently probing the same representation;
- duplicate orchestration paths;
- an optional extension importing core internals;
- a helper that became a de facto public protocol without admission.

### 13.6 Generic-hook analysis

For each generic declared as a protocol stage, report:

- total methods;
- default/fallback methods;
- concrete specializations;
- callers;
- whether the generic is exported or imported cross-owner;
- whether any specialization changes behavior.

A hook with one identity default and no real specialization is dead architecture.

### 13.7 Diff-scoped authority budget

Every pull request should report:

```text
Semantic authorities before:
Semantic authorities after:
New generic names:
New methods on existing generics:
New abstract types:
New wrapper types:
New modules:
New registries:
New compatibility paths:
New cross-owner edges:
New suppressions:
Removed authorities:
Removed execution paths:
```

For cleanup/refactor work, any positive value in the “new authority” fields requires an explicit task-level exception and warrant.

### 13.8 Suppression format

A suppression is allowed only for a proven external or compatibility boundary and records:

```toml
rule = "NSE006"
construct = "exact qualified symbol"
owner = "PackageNameDependencyExt"
external_system = "DependencyName"
affected_versions = ">= 1.2, < 1.4"
issue = "upstream issue or documented contract"
test = "test/extensions/dependency_workaround.jl"
removal_condition = "DependencyName >= 1.4"
review_after = "YYYY-MM-DD"
```

Do not maintain a whitelist of ordinary internal helpers. If an internal construct needs a permanent suppression, the policy has already lost the argument.

### 13.9 Absence guards

A convergence change is not complete until searches prove that retired constructs are absent from active:

- source;
- package extensions;
- tests;
- maintained documentation;
- examples;
- scripts participating in supported workflows.

Historical archives may retain old text when explicitly excluded from active documentation.

### 13.10 Metrics that do not prove convergence

Do not use the following as standalone evidence:

- fewer lines of code;
- smaller average function length;
- lower cyclomatic complexity;
- more files;
- more test cases;
- higher comment density;
- more abstract types;
- a cleaner dependency diagram.

The relevant question is whether ownership, semantic authority, and execution paths became simpler.

---

## 14. Repository-specific adoption without overfitting

### 14.1 The general playbook remains unchanged

Do not edit this document to list current repository symbols, current defects, or one campaign’s deletion targets.

Project-specific facts belong in a separate profile or finite refactor prompt. This prevents one bad implementation snapshot from becoming universal doctrine through copy and paste, humanity’s most efficient standards body.

### 14.2 Inspect the live repository

Before applying the policy, inspect the current live repository rather than relying on memory or retained snippets.

At minimum inspect:

- repository instructions;
- package and module entry files;
- public API and maintained architecture documentation;
- current tests and CI;
- optional extensions;
- release tags and compatibility commitments;
- the current call graph;
- recent relevant refactors;
- current `git status`;
- the exact task preservation contract.

### 14.3 Evidence classification

Classify every reviewed construct as:

| Classification | Meaning |
|---|---|
| `NATIVE` | Core, Base, standard library, or dependency interface owns the meaning. Use it. |
| `OWNED` | The repository owns a stable domain action, invariant, algorithm, lifecycle, or protocol that passes admission. |
| `BOUNDARY` | The construct isolates a proven external or compatibility contract. |
| `DEBT` | The construct forwards, duplicates, probes, glues, or normalizes without semantic delta. Remove or collapse it. |
| `UNPROVEN` | Evidence is insufficient. Do not formalize or reuse it until proof exists. |

There is no `LEGACY_BUT_PROBABLY_IMPORTANT` classification. That category is where dead APIs go to acquire tenure.

### 14.4 Repository profile template

Create a separate current artifact with this shape:

```text
# Native-First Semantic Economy Repository Profile

Repository:
Branch and commit:
Profile date:
Language/runtime versions:

## Preservation contract
- numerical behavior:
- public workflows:
- persisted formats:
- visual/report artifacts:
- external integrations:

## Proven compatibility obligations
- consumer or format:
- supported versions:
- removal condition, if temporary:

## Owner map
- concept:
- owner:
- public action/result:

## Admitted shared interfaces
- native/dependency interfaces:
- project-owned generics:
- extension seams:

## Approved external shims
- suppression records:

## Current semantic-authority baseline
- generics:
- types:
- modules:
- registries:
- aliases:
- execution paths:

## Project-specific hard residue searches
- retired symbols:
- prohibited files/modules:
- private cross-owner imports:

## Validation commands
- focused tests:
- full tests:
- integration tests:
- numerical/visual/report baselines:
- ambiguity/inference checks:
- formatter and diff checks:
```

The profile may tighten this playbook. It may not legalize zero-semantic-delta internal glue.

### 14.5 Examples and historical documents remain non-normative

When a project guide includes example code, label the example as one of:

- `ILLUSTRATIVE`;
- `CURRENT VERIFIED IDIOM` with commit/date evidence;
- `ANTI-EXAMPLE`;
- `HISTORICAL`.

An unlabelled old snippet is not an implementation instruction.

---

## 15. Audit and convergence procedure

### Step 1: state the preservation contract

Record exactly what must remain:

- numerical results and tolerances;
- public workflows;
- released APIs;
- persisted formats;
- external integrations;
- visual and report artifacts;
- safety and transaction behavior.

Separate those from obsolete implementation shape.

### Step 2: inventory semantic authorities

Enumerate:

- generic names;
- types and wrappers;
- modules;
- registries;
- aliases and deprecations;
- public entry points;
- orchestration paths;
- private cross-owner calls;
- selector, unit, validation, metadata, and serialization maps.

### Step 3: classify every authority

Assign `NATIVE`, `OWNED`, `BOUNDARY`, `DEBT`, or `UNPROVEN`.

Existing code receives no automatic exemption.

### Step 4: map replacements

For every `DEBT` or `UNPROVEN` construct, inspect:

- native Julia interfaces;
- dependency interfaces;
- existing admitted generics;
- constructors and promotion;
- direct owner-local code;
- one coherent cutover to a single contract.

### Step 5: inspect callers and methods

Determine:

- actual production callers;
- actual method family;
- cross-owner imports;
- whether callers share semantics or only syntax;
- whether the construct is a real extension seam;
- whether removal simplifies ownership and execution.

### Step 6: apply the companion playbooks

For each surviving concept:

- assign one owner;
- place it by owner and responsibility;
- keep optional dependencies in extensions;
- reject catch-all modules.

For each surviving first-class action:

- keep the choreography visible;
- turn only real variation into dispatched hooks;
- remove decorative stages, contexts, and entitlement registries.

### Step 7: perform the smallest coherent cutover

Migrate all consumers to one contract and delete:

- old names;
- wrappers;
- shims;
- aliases;
- duplicated registries;
- stale tests;
- stale docs;
- private cross-owner paths.

Do not leave old and new architecture in parallel for a mythical later cleanup.

### Step 8: validate behavior and absence

Run repository-native:

- focused tests;
- full tests;
- numerical baselines;
- external integration tests;
- visual/report/workbook fixtures;
- inference and allocation checks where relevant;
- method ambiguity checks;
- AST and call-graph guardrails;
- retired-symbol searches;
- formatting and `git diff --check`.

### Step 9: report findings

Use this record:

```text
Finding:
Construct:
Owner:
Current source evidence:
Classification:
Native or existing authority:
Claimed semantic delta:
Current callers and methods:
Violation or warrant:
Required action:
Behavior to preserve:
Tests and baselines:
Guardrail rule:
Residue search:
```

Do not report a construct as removed while preserving it through an alias or wrapper.

---

## 16. Pull-request acceptance checklist

### Evidence and scope

- [ ] The current live repository, not remembered or archived code, was inspected.
- [ ] The preservation contract is explicit.
- [ ] Examples and historical documents were treated as evidence, not authority.
- [ ] The change does not silently preserve an unreleased implementation shape.

### Native precedence

- [ ] Core, Base, standard-library, and dependency interfaces were checked first.
- [ ] No project-owned query duplicates collection, type, display, conversion, or iteration semantics.
- [ ] Constructors and native promotion handle owned numeric construction.
- [ ] No lossy transformation is disguised as conversion or coercion.

### Semantic authority

- [ ] Every new generic, type, module, wrapper, registry, or compatibility path has an approved warrant.
- [ ] Every new name adds a stated semantic delta.
- [ ] Method count and generic-name count are reported separately.
- [ ] Cleanup/refactor authority and execution-path counts are non-increasing.

### Helpers

- [ ] No exact forwarding wrapper was added.
- [ ] No one-caller module-level helper merely repacks, merges, forwards, or reads fields.
- [ ] Algorithm-local functions remain local.
- [ ] Coherent one-caller kernels were not falsely deleted merely because they are private.
- [ ] No catch-all helper/common/utils artifact was introduced.

### Shims and compatibility

- [ ] No internal shim remains.
- [ ] Every external workaround has version/capability evidence, tests, an owner, and a removal condition.
- [ ] Every compatibility path names a released consumer or format.
- [ ] No old/new parallel path survives the cutover.

### Dispatch and Template Method

- [ ] Existing generic functions were extended instead of duplicated.
- [ ] Only genuinely variable stages are generic hooks.
- [ ] Required hooks have no silent broad fallback.
- [ ] Optional hooks have at least one current nontrivial specialization.
- [ ] Entitlement does not mirror method availability.
- [ ] The public choreography remains visible in one owner.
- [ ] No manager, context, or `_run_pipeline` hides the action.

### Ownership and layout

- [ ] Every surviving concept has one owner.
- [ ] Siblings and extensions do not call underscore-prefixed names.
- [ ] Optional dependency behavior lives in the owning extension.
- [ ] Base methods live with the owned types in protocol files.
- [ ] No submodule or file exists solely to hide private methods.

### Julia API behavior

- [ ] Methods ending in `!` mutate an advertised argument on every successful path.
- [ ] Human display uses `show` or `showerror` where appropriate.
- [ ] Collections use Base interfaces.
- [ ] Internal callback and extension signatures are explicit.
- [ ] Runtime source does not use exception probing or `eval` as an owned protocol.

### Validation

- [ ] Behavior tests and preserved baselines pass.
- [ ] External integrations were tested against real boundaries.
- [ ] Method ambiguity and inference checks pass where relevant.
- [ ] AST and call-graph guardrails pass.
- [ ] Retired symbols and files are absent from active repository surfaces.
- [ ] `git diff --check` passes.

---

## 17. Agent implementation directive

Use this block in repository instructions or task prompts:

```text
NATIVE-FIRST SEMANTIC ECONOMY

Treat the current task and live repository as the evidence base. Do not treat remembered code, old branches, retained snippets, previous prompts, tests, examples, or generated guides as doctrine.

Before creating any project-owned generic function, type, wrapper, trait, stage, registry, context, alias, module, compatibility path, or helper:

1. Check Core, Base, the standard library, dependency-owned interfaces, constructors, and existing admitted repository generics.
2. Prefer direct owner-local code when no stable reusable semantics exist.
3. Prefer another method of an existing generic over a new generic name.
4. Record the new construct's owner, semantic delta, current callers, current method family, warrant, invariant/result contract, and tests.
5. Reject the construct when it merely forwards, renames, repacks, merges defaults, reads fields, hides choreography, bridges two package-owned representations, duplicates native behavior, or anticipates hypothetical reuse.
6. Keep algorithm-local functions local. A coherent algorithm may remain private even with one caller.
7. Do not introduce internal shims. Repair the owner contract, migrate all consumers, and delete the old path.
8. Admit external shims only with a named external system, affected version/capability range, real integration test, owner, and removal condition.
9. Do not add compatibility without a named released consumer or versioned format.
10. During cleanup and convergence work, new semantic authorities and execution paths default to zero. Method count may increase; generic-name count may not without explicit approval.
11. Apply Ownership-Centered Recursive Module Layout only to admitted concepts.
12. Apply Dispatch-Driven Template Method only to admitted first-class actions, and make only genuinely variable stages generic hooks.
13. Do not create Utils, Helpers, Common, Shared, Misc, manager, provider, context, adapter, or registry infrastructure without an independently proven semantic owner.
14. Run repository-native behavior tests, architecture guardrails, call-graph checks, residue searches, and diff checks before completion.
```

---

## 18. Compact normative form

> **Use Core, Base, standard-library, dependency-owned interfaces, constructors, native promotion, and admitted repository generics before creating project-owned abstractions. Existing code, tests, prompts, examples, snapshots, and generated guides are evidence subject to scrutiny, not precedent. Every new generic function, type, wrapper, trait, stage, registry, context, alias, module, or compatibility path must add a stable semantic delta by owning a domain action, invariant, real dispatch seam, coherent algorithm, lifecycle, external boundary, supported compatibility contract, or measured performance boundary. Mere forwarding, renaming, field access, tuple repacking, default merging, internal representation bridging, malformed-contract normalization, speculative extensibility, and duplication of native behavior are forbidden. Small methods extending an existing interface are encouraged. New one-method generic names are presumptively defective. Internal mismatches are repaired at their owners, never shimmed. During cleanup and convergence refactors, semantic authorities and execution paths must not increase.**

---

## 19. Mechanical policy block

```text
NATIVE-FIRST SEMANTIC ECONOMY

1. Current live evidence outranks retained examples and historical code.
2. Every new name must add semantic information.
3. Search native and dependency interfaces before project-owned abstractions.
4. Direct owner-local code precedes helper extraction.
5. Methods on admitted generics may increase; new generic names require a warrant.
6. New module-level private generic names default to zero in cleanup/refactor work.
7. Reject exact forwarders, field wrappers, tuple repackers, default-merging helpers, and native duplicate queries.
8. Keep local implementation functions local; admit one-caller kernels only for coherent algorithms.
9. Reject internal shims and package-owned structural-probing bridges.
10. Require external shims to be isolated, scoped, tested, and removable.
11. Require compatibility to name a released consumer or versioned format.
12. Reject catch-all Utils/Helpers/Common/Shared/Misc modules and files.
13. Reject exception-based internal protocol discovery and runtime eval-based owned grammar.
14. Reject registries that mirror dispatch and layers that repeat the same abstraction.
15. Require truthful ! methods, native collection interfaces, native display protocols, constructors, and promotion.
16. Apply ownership layout only after admission.
17. Apply Template Method only to admitted actions and actual variable stages.
18. Track semantic-authority and execution-path counts in every refactor diff.
19. Permit suppressions only for proven external or compatibility boundaries.
20. Validate both preserved behavior and absence of retired machinery.
```

---

## 20. References and conceptual foundation

This playbook is a project-operational synthesis, not an ISO standard.

### Information hiding and decomposition

- D. L. Parnas, “On the Criteria To Be Used in Decomposing Systems into Modules,” *Communications of the ACM*, 15(12), 1972. DOI: <https://doi.org/10.1145/361598.361623>

Parnas provides the foundation for decomposing around owned design decisions and information rather than arbitrary processing fragments.

### Deep modules and layer discipline

- John K. Ousterhout, *A Philosophy of Software Design*, 2nd edition.
- Stanford materials on abstraction and modular design: <https://web.stanford.edu/~ouster/>

Relevant concepts include deep modules, shallow interfaces, pass-through methods, information leakage, and “different layer, different abstraction.”

### DRY as duplicated knowledge

- David Thomas and Andrew Hunt, *The Pragmatic Programmer*, 20th Anniversary Edition.
- Dave Thomas, “Premature Design Is Not Design”: <https://articles.pragdave.me/p/premature-design-is-not-design>

The relevant distinction is duplicated knowledge versus duplicated syntax.

### Julia language authority

- Julia Manual, Methods: <https://docs.julialang.org/en/v1/manual/methods/>
- Julia Manual, Interfaces: <https://docs.julialang.org/en/v1/manual/interfaces/>
- Julia Manual, Constructors: <https://docs.julialang.org/en/v1/manual/constructors/>
- Julia Manual, Conversion and Promotion: <https://docs.julialang.org/en/v1/manual/conversion-and-promotion/>
- Julia Manual, Style Guide: <https://docs.julialang.org/en/v1/manual/style-guide/>
- Julia Manual, Performance Tips: <https://docs.julialang.org/en/v1/manual/performance-tips/>
- Julia Manual, Modules: <https://docs.julialang.org/en/v1/manual/modules/>

### Companion playbooks

- *Ownership-Centered Recursive Module Layout Playbook*
- *Dispatch-Driven Template Method Playbook for Julia*

The companion playbooks govern placement and choreography only after this playbook admits the concept.

---

## 21. Final rule

A repository is converging when ordinary work becomes simpler:

1. use the operation the language already owns;
2. add a method when one admitted operation varies by type;
3. write direct owner-local code when no reusable semantic unit exists;
4. name first-class actions and coherent algorithms, not expressions;
5. isolate real external boundaries;
6. delete internal glue rather than formalizing it;
7. keep fixed choreography visible;
8. let constructors, promotion, collections, display, and dispatch do their jobs;
9. distrust inherited abstractions until they survive the same review as new ones;
10. remove old paths completely after a finite cutover.

The purpose is not to forbid abstraction. The purpose is to stop granting permanent names to temporary implementation discomfort.
