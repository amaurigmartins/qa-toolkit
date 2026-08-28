# Dispatch-Driven Template Method Playbook for Julia

> **Closed choreography. Open dispatch. One action owner. One owned result. Definitions declare; orchestrators execute.**

## Status and intended use

This document is a project-wide architectural playbook for extensible Julia subsystems. It applies to plotting, validation, data entry, error handling, unit handling, result access, import/export, backends, formulations, builders, and any later computation workflow that has a stable execution skeleton with type-specific variation.

It is not a demand to force every function into a framework. It is a rule for **first-class extensible actions**: operations whose workflow should remain predictable while new domain types, definitions, backends, rules, observables, or result forms are added.

The underlying ingredients are established ideas:

- **Template Method** fixes the skeleton and ordering of an algorithm while allowing selected steps to vary.
- **Hook methods** represent the replaceable or optional steps.
- **Inversion of control** means the orchestrator owns the sequence and invokes extensions, rather than extensions creating their own workflow.
- **Julia informal interfaces** use a small set of generic functions as the contract implemented by concrete types.
- **Multiple dispatch** selects stage behavior from the participating types.

The exact compound phrase **dispatch-driven Template Method implemented through a total informal interface** is the project convention defined here. “Total informal interface” is not official Julia terminology. It means that the protocol is complete over the domain it explicitly admits.

This playbook strengthens the existing architectural convergence rules: one authority per concept, predictable extension paths, semantic access through exported methods, and no decorative protocols that ordinary consumers bypass.

---

## 1. Pattern definition

A subsystem follows this playbook when it has:

1. one owning module;
2. one public action;
3. one explicit ordered stage sequence;
4. atomic generic functions for the stages;
5. specialization selected by dispatch;
6. explicit defaults for legitimate non-applicable stages;
7. an explicit rejection boundary for unsupported inputs;
8. one final result owned by the action’s module;
9. one semantic read protocol for generic downstream consumers.

For an action `run`, definition `d`, input `x`, stage sequence `s₁ … sₙ`, and result constructor `m`, the architecture is:

```text
run(d, x) = m(sₙ(...s₂(s₁(d, x))...))
```

The order belongs to `run`. The behavior of each `sᵢ` belongs to the method selected for the concrete argument types.

### Julia translation of the classic pattern

The classic object-oriented Template Method is usually presented as a base-class method calling overridable subclass methods. That inheritance machinery is not the useful part. In Julia:

- the **template method** is the public orchestrator generic function;
- the **hooks** are top-level generic functions;
- the **subclass override** becomes a more specific method;
- the **abstract class contract** becomes an informal interface;
- the **strategy object**, when genuinely needed, is a concrete definition/backend/formulation value participating in dispatch.

No class hierarchy cosplay is required. Humanity survives another day without an `AbstractEnterpriseTemplateMethodFactory`.

---

## 2. Core laws

### 2.1 One action owner

Every first-class action has one module that owns:

- accepted inputs;
- public orchestrator;
- stage interface;
- final result type;
- invariants of that result;
- conformance tests.

An orchestration module that owns neither the action nor its result is presumptively misplaced.

### 2.2 One public orchestrator

There is one obvious entry point such as:

- `plot(definition, source)`;
- `validate(entry)`;
- `enter(definition, raw)`;
- `render_quantity(value, quantity)`;
- `export_result(definition, source)`;
- `compute(problem, formulation)`.

Convenience constructors and shorthand functions delegate to this path. They do not recreate it.

### 2.3 Closed choreography

The orchestrator shows the complete high-level sequence as a boring list of named operations. Stage order is not duplicated across methods, backends, or call sites.

The choreography is closed to routine extension. Adding a supported type should not require adding another branch to the orchestrator.

### 2.4 Open dispatch

Variation is introduced by adding methods for concrete combinations of:

- definition type;
- input/result type;
- backend type;
- formulation type;
- rule type;
- observable descriptor type;
- error-handler type.

Types carry semantic distinctions. Symbols and strings may exist at user or serialization boundaries, but they are normalized once into typed objects before the extensible core executes.

### 2.5 Atomic stages

Each stage:

- has one short action name;
- owns one semantic responsibility;
- has explicit inputs and outputs;
- is independently testable;
- is defined at module scope;
- does not hide another orchestration graph.

A stage may contain loops and data-dependent branches that belong to its domain algorithm. The prohibition is against scattering **architectural policy selection** through `if`, `mode`, `style`, `kind`, key, or registry decoding.

### 2.6 Explicit non-applicability

A stage that belongs to the protocol but legitimately does nothing for a supported type has an explicit identity or no-op method.

Examples:

```julia
normalize_input(::MyDefinition, input::MyInput) = input
place_legend!(::MyBackend, target, panels, ::NoLegendPlot) = nothing
postprocess(::MyDefinition, raw, ::NoContext) = raw
```

Optionality is not inferred by catching `MethodError`, probing fields, or asking whether a symbol happens to exist.

### 2.7 Unsupported means unsupported at the boundary

A type pair outside the supported domain fails before partial execution. Use one explicit entitlement predicate or let the public dispatch surface reject the call immediately.

Unsupported and optional are different:

- **unsupported**: the action is not defined for that combination;
- **optional**: the action is supported and a named stage intentionally resolves to identity/no-op.

### 2.8 Definitions declare; orchestrators execute

A `Definition` is passive policy data. It may hold user choices, dimensions, quantities, limits, or backend-independent configuration. It does not:

- run the pipeline;
- discover its own handlers;
- mutate runtime lifecycle state without a concrete reason;
- decode generic `mode` or `style` fields into behavior;
- become an alternate result wrapper.

Behavior associated with a definition is expressed by methods dispatched on its concrete type.

### 2.9 One owned result

The public action returns the completed result owned by its module. A trace may retain diagnostics and intermediate artifacts, but `trace.result` must remain the actual completed owned result, not a shadow representation.

### 2.10 One semantic read protocol

Cross-module consumers read owned results through exported semantic functions. They do not each invent their own field access, selectors, DataFrame schema, or datasource keys.

Inside the owner and justified hot numerical kernels, direct fields remain legitimate. Outside that boundary, use the result protocol, such as `observables` and `observe`.

---

## 3. What “total informal interface” means

Let:

- `D` be the set of definition/strategy types;
- `X` be the set of input types;
- `A ⊆ D × X` be the explicitly admitted combinations;
- `S = (s₁, …, sₙ)` be the ordered stage interface.

The interface is **total over `A`** when all of the following hold:

1. membership in `A` is explicit through dispatch or an entitlement method;
2. every required stage is applicable for every admitted combination;
3. every optional stage has a defined identity/no-op method over the admitted domain;
4. each stage returns a value accepted by the next stage;
5. every admitted execution reaches one owned result type or a documented domain failure;
6. unsupported combinations fail before side effects or partial materialization;
7. ordinary extension adds methods locally instead of editing a central decision tree.

Total does **not** mean:

- every type in the universe is accepted;
- no method may throw;
- invalid domain data magically becomes valid;
- every hook receives a broad fallback that silently hides missing implementations.

### Required, optional, and derived hooks

Every interface method must be classified.

| Hook class | Meaning | Default policy |
|---|---|---|
| Required | The action cannot produce its result without it. | No silent default. Missing implementation is an interface defect. |
| Optional | The stage semantically exists but may do nothing. | Explicit identity/no-op. |
| Derived | Generic behavior can be implemented from required hooks. | Provide the generic implementation; specialize only for semantics or performance. |
| Boundary normalization | Converts user/external syntax into owned typed values. | Perform once before the core choreography. |

A broad fallback for a required hook turns an interface defect into delayed nonsense. A missing optional hook turns legitimate non-applicability into accidental failure. Both are bad, merely in different costumes.

---

## 4. Standard subsystem anatomy

An extensible subsystem should be explainable with the following protocol card.

```text
Action:
Owner:
Public orchestrator:
Accepted input domain:
Declarative definition/strategy types:
Final owned result:
Entitlement boundary:
Ordered stage sequence:
Required hooks:
Optional hooks and defaults:
Derived hooks:
Semantic result-access protocol:
Allowed direct representation access:
Normal extension path:
Conformance tests:
Performance contract:
```

If these fields cannot be filled without a séance, the subsystem does not yet have a coherent extension model.

### Recommended participants

Use only participants that own a real role:

- **Definition**: passive intent and policy.
- **Input/domain object**: source data accepted by the action.
- **Context/workspace**: runtime state that genuinely crosses stages.
- **Backend/formulation/rule/descriptor**: concrete dispatch axis with domain meaning.
- **Result**: final owned product.
- **Trace/report**: optional diagnostics that contain, rather than replace, the result.

Do not invent all six for every subsystem. A unit protocol may need only quantity descriptors and methods. A validator may need entries, rules, and handlers. The playbook is a constraint on ownership and choreography, not a collectible-card game.

---

## 5. Designing the choreography

### 5.1 Start from the final result

Before naming stages, state the result and its owner.

Bad starting question:

> What abstractions could make this flexible?

Correct starting questions:

1. What completed object must this action return?
2. Which module owns that object end-to-end?
3. What invariant separates the completed object from intermediate state?
4. Which consumers need semantic access afterward?

The stage sequence follows from the result. Otherwise the design tends to produce contexts, managers, and traces in search of a reason to exist.

### 5.2 Name stages as domain actions

Use verbs that describe actual work:

```text
parse → normalize → validate → construct
fetch → panelize → draw → decorate → present
select → tabulate → encode → write
initialize → assemble → reduce → materialize
```

Avoid vague stages such as:

```text
process → handle → manage → resolve → apply → finalize
```

Those names may be valid only when the subsystem gives them precise domain meaning. Generic nouns are where responsibilities go to hide from the police.

### 5.3 Keep the orchestrator visibly complete

The public method should read as the full architecture. Do not bury the sequence in a private `_run_pipeline`, nested local function, function factory, closure chain, or manager object.

A top-level semantic method used by more than one action is legitimate. A shadow helper whose only purpose is to conceal the real choreography is not.

### 5.4 Separate architecture from kernels

The orchestrator chooses **when** domain kernels run. Kernels own the heavy mathematics, loops, preallocation, and data-dependent branching.

```text
compute
  normalize problem
  validate formulation
  initialize workspace
  assemble matrices        ← numerical kernel may be complex
  reduce system            ← numerical kernel may branch on data
  materialize result
```

The fixed sequence should not be rejected merely because `assemble!` is sophisticated. The whole point is that the sophisticated thing has one obvious place to live.

### 5.5 Contexts must earn their existence

Use a context/workspace only when state truly crosses several stages or must be reused/preallocated.

A valid context owns:

- preallocated buffers;
- stable backend handles;
- resolved layout state;
- transaction state;
- diagnostics accumulated across stages.

An invalid context is a bag of everything passed everywhere to avoid writing precise signatures.

Prefer concrete parametric fields. Do not use `Dict{Symbol,Any}` as an architectural nervous system unless the external boundary genuinely requires untyped data, and normalize it before the hot path.

---

## 6. Choosing dispatch axes

Dispatch on types that represent real semantic distinctions.

### Primary axes

Common valid axes are:

```julia
stage(definition::PlotDefinition, source::LineParameters)
stage(rule::Positive, entry::CableGeometryEntry)
stage(backend::CairoBackend, artifact::PlotArtifact)
stage(observable::SeriesImpedance, result::LineParameters)
stage(formulation::AnalyticalFormulation, problem::LineParametersProblem)
```

### Boundary values versus core types

User syntax may reasonably contain symbols:

```julia
plot(result; quantity = :series_impedance)
```

Normalize that once:

```julia
observable(::Val{:series_impedance}) = SeriesImpedanceObservable()
```

Then carry the typed descriptor. Do not repeatedly decode `:series_impedance` throughout plotting, exporting, UQ, and reporting.

### When to use traits

Use trait dispatch only for an orthogonal property that:

- cannot be represented cleanly by the existing type hierarchy;
- is shared by unrelated types;
- materially changes a stage implementation;
- has a small stable trait domain.

Do not create a trait merely to avoid writing two ordinary methods. Traits are an escape hatch for orthogonal classification, not a second shadow type system.

### Do not encode bulk runtime data in types

Dispatch should express a bounded set of semantic alternatives. Do not place arbitrary IDs, labels, frequencies, user names, matrix sizes, or large runtime taxonomies in type parameters. Julia’s own performance guidance warns that abusing values-as-parameters can create a combinatorial explosion of specializations.

---

## 7. Definitions and declarative grammar

A declarative layer is valid when it captures intent once and allows the orchestrator to remain stupid.

### A valid definition

```julia
struct ImpedanceMagnitudePlotDefinition{L}
    layout::L
end

observable_requests(::ImpedanceMagnitudePlotDefinition) = (
    FrequencyObservable(),
    SeriesImpedanceObservable(),
)
```

The definition contains policy data. Methods define what that concrete declaration means.

### Invalid declarative drift

```julia
struct PlotDefinition
    mode::Symbol
    style::Symbol
    family_key::Symbol
    options::Dict{Symbol,Any}
end
```

followed by:

```julia
if definition.mode === :comparison
    ...
elseif definition.mode === :distribution
    ...
end
```

That is a data-driven switchboard pretending to be declarative architecture.

### Legitimate value fields

A field is legitimate when it is genuinely runtime data rather than a disguised behavior selector:

- requested frequency limits;
- title text;
- output path;
- numeric tolerance;
- panel dimensions;
- chosen unit value;
- explicit user label.

The test is simple: does changing the field choose a fundamentally different method family? If so, a concrete type may be the honest representation.

---

## 8. Result ownership and observables

### 8.1 Representation belongs to the owner

The result owner controls construction and internal representation. Other modules should not depend on incidental field layout.

Julia’s style guide explicitly recommends exported methods over direct field access because methods preserve implementation freedom and describe conceptual operations across types.

### 8.2 Observables are typed semantic descriptors

An observable grammar should define:

- which observables a result exposes;
- how each observable is extracted;
- its semantic quantity;
- axes/domain metadata;
- label and unit information;
- any supported reductions or selectors.

Prefer descriptor types:

```julia
struct FrequencyObservable <: AbstractObservable end
struct SeriesImpedanceObservable <: AbstractObservable end

observe(result::LineParameters, ::FrequencyObservable) = result.f
observe(result::LineParameters, ::SeriesImpedanceObservable) = result.Z
```

The direct field access is implemented beside the owning result. PlotBuilder, exporters, benchmarks, DataFrames, and UQ call `observe`.

### 8.3 One extraction grammar

The following may not coexist as independent authorities:

- direct cross-module accessors;
- plot-only datasource keys;
- Monte Carlo selector taxonomies;
- export column keys;
- observables;
- a second wrapper that republishes the same values.

Adapters may project observables into a DataFrame or plotting series, but they derive from the same protocol.

### 8.4 Metadata is not execution policy

Observable metadata may contain labels, dimensions, and units. It should not carry functions or `mode` fields that recreate consumer behavior. Consumers dispatch on observable and definition types.

---

## 9. Validation, DataEntry, and ErrorHandler

Validation is one of the clearest applications.

### 9.1 Ownership split

- **DataEntry** owns the intake choreography: parse, normalize, validate, construct.
- **Validation** owns rule declarations and rule evaluation.
- **ErrorHandler** owns what happens to structured issues: throw, collect, log, or render.
- The domain module owns domain-specific rules and the final constructed object.

No module should absorb the others into one enormous `validate` function full of branches.

### 9.2 Rules are values with dispatched evaluation

A rule tuple returned by dispatch is not a global registry. It is type-owned declarative policy:

```julia
rules(::Type{<:CableGeometryEntry}) = (
    Nonnegative{:r_in}(),
    Positive{:r_ex}(),
    LessThan{:r_in,:r_ex}(),
)
```

Each rule has one `check(rule, entry)` method. The validator applies the tuple in order. Adding a domain rule adds a rule type/method and extends the tuple for the owning entry type.

### 9.3 Error handling is a second dispatch axis

```julia
handle!(::ThrowingHandler, issue)
handle!(::CollectingHandler, issue)
```

The rule does not decide whether to throw, collect, print, or paint the GUI red. It reports a structured issue. The handler owns reaction policy.

### 9.4 Invalid, unsupported, and failed are distinct

- **Invalid input**: the action supports the type, but the data violate a rule.
- **Unsupported input**: no valid action exists for that type combination.
- **Execution failure**: accepted input reached a real external or numerical failure.

Do not flatten all three into strings emitted from one universal error function.

---

## 10. PlotBuilder

PlotBuilder should be a declarative interpreter with a fixed materialization sequence.

### Recommended choreography

```text
check entitlement
request observables
fetch semantic data
create target/window
create panels
derive series
draw
place legend
attach controls/callbacks
finalize render artifact
```

### Extension points

Dispatch may vary:

- source entitlement;
- requested observables;
- panel definitions;
- grouping;
- series construction;
- backend target creation;
- drawing primitive;
- legend policy;
- controls and callbacks;
- final artifact.

### What PlotBuilder must not do

- inspect result fields directly outside the observable owner;
- infer plot families from storage shapes when definitions already declare them;
- maintain parallel plot-only quantity keys;
- keep unused generic `mode`, `recipe`, or `style` branches;
- make definitions execute themselves;
- let each backend reimplement the whole orchestration sequence.

Makie recipes are a useful external case study for extending plotting through typed conversions and dispatched plotting methods. They are not a command to mirror Makie’s internal architecture wholesale.

---

## 11. UnitHandler

UnitHandler is primarily an informal interface and may use a short Template Method for rendering/conversion.

### Quantity protocol

For each typed quantity descriptor define:

```text
native unit
preferred display unit
label
symbol
conversion behavior
optional formatter
```

### Fixed rendering sequence

```text
obtain native unit
obtain display unit
convert value
format value
attach semantic label/symbol
```

### Rules

- Quantity semantics are typed; display text is data.
- Conversion checks dimension compatibility through dispatch/type parameters.
- PlotBuilder, exporters, and observables reuse UnitHandler rather than cloning labels and scale factors.
- Do not infer units from field names in every consumer.
- Do not let a generic `style` field decide whether a value is absolute, relative, logarithmic, RMS, or phase. Those are semantic concepts and deserve real names/types.

---

## 12. Import, export, and adapters

These operations fit the same structure when they have stable stages.

### Import/DataEntry

```text
read raw source
parse syntax
normalize external values
validate domain entry
construct owned object
```

### Export

```text
select observables
project to tabular/structured representation
encode backend format
write destination
return export artifact
```

Backends should be typed objects such as `CSVBackend`, `JSONBackend`, or `XLSXBackend`, not `format = :csv` decoded inside the core. A user symbol may be normalized to a backend at the boundary.

Adapters are justified when they isolate a genuine external contract. They are not justified when they forward one call unchanged to another module.

---

## 13. Computation pipelines

Computation may adopt the same pattern later, provided the physics owner and result owner remain unambiguous.

A candidate high-level choreography is:

```text
normalize problem
validate problem/formulation pair
initialize concrete workspace
assemble physical contributions
apply reductions/transformations
materialize owned result
```

Important constraints:

- `compute` owns the full path to the completed result;
- mutating scratch buffers does not make a non-mutating public API `compute!`;
- formulation types select kernels through dispatch;
- parametric and UQ layers repeat `compute`; they do not own fragments of it;
- a trace contains the final result rather than substituting a trace-specific result type;
- numerical kernels remain free to optimize internally.

This section is a seed, not an instruction to refactor the computation pipeline immediately.

---

## 14. Performance rules

The architecture is intended to cooperate with Julia’s compiler, not merely look tidy in a diagram.

### Required discipline

- concrete parametric fields in hot objects;
- no `Function`-typed fields for extensibility;
- callable functor structs when behavior must be carried as data;
- no captured closures as public extension points;
- type-stable stage returns for each concrete method path;
- tuples for small static protocol collections such as rule sets;
- vectors only when cardinality is genuinely runtime-dynamic;
- function barriers between dynamic boundary normalization and specialized kernels;
- preallocated workspaces only when measurements prove repeated allocation matters;
- `!` only when a caller-visible argument is mutated, excluding ordinary RNG/IO conventions;
- no broad `Any` context threaded through hot stages;
- no `Val(runtime_symbol)` inside hot loops.

### The orchestrator is not necessarily the hot loop

A dynamic user boundary may normalize strings, symbols, files, or dictionaries. The orchestrator should cross a function barrier into concrete typed stages. The hot kernels then specialize on resolved types.

### Measure instead of chanting

For representative paths use repository-native tools such as:

- `@inferred`;
- `@code_warntype`;
- allocation benchmarks;
- method ambiguity checks;
- benchmark baselines;
- numerical result baselines.

Do not contort the public grammar for an unmeasured micro-optimization. Do not keep an obviously unstable protocol because the tests happen to be green.

---

## 15. Conformance and testing

Every extensible subsystem needs tests for both behavior and architecture.

### 15.1 Choreography test

Use a minimal instrumented implementation that records stage calls. Assert exact order and exactly-once execution.

```text
normalize
check
initialize
prepare
perform
postprocess
materialize
```

This catches backend-specific pipelines that quietly skip or duplicate stages.

### 15.2 Entitlement test

For each supported pair:

- the action succeeds or reaches a documented domain error;
- required hooks are applicable;
- optional hooks resolve to explicit defaults when not specialized.

For unsupported pairs, failure occurs before side effects.

### 15.3 Extension-locality test

Create a tiny test-only extension type. Adding it should require only:

- the new concrete type;
- its required stage methods;
- its tests.

If the test must edit a central switch, registry, parser, plot family table, and export mapping, the architecture is lying about extensibility.

### 15.4 Result-ownership test

Assert the public action returns the owner’s result type. If a trace exists:

```julia
@test trace.result isa OwnedResult
```

### 15.5 Observable-discipline test

Test that generic consumers use the observable protocol. Where practical, create a result whose representation differs but whose observable methods are equivalent. Consumers should continue working.

### 15.6 Rule-order and handler tests

For validation:

- rules execute in declared order;
- throwing and collecting handlers receive the same issues;
- no-op/default rule bundles remain valid;
- custom domain rules require no validator modification.

### 15.7 Type stability and ambiguity

Test representative concrete paths with `@inferred`. Run method ambiguity checks after adding extension axes. Multiple dispatch is excellent until someone defines two equally plausible methods and the compiler responds with the software equivalent of folded arms.

### 15.8 Numerical and external baselines

Architectural cleanup must preserve:

- validated numerical outputs and tolerances;
- orientation/order/units;
- real external-tool integration behavior;
- deterministic semantics where promised.

Architecture tests supplement these baselines. They do not replace physics.

---

## 16. Failure signatures and prohibited drift

Treat the following as review failures unless a concrete boundary justifies them.

### Ownership drift

- two modules export competing versions of one action;
- an orchestration module owns neither input nor result;
- traces or wrappers replace the owned result;
- convenience APIs bypass the main choreography.

### Switchboard drift

- growing `if`/`elseif` on type-like symbols;
- generic `mode`, `style`, `kind`, or family-key fields decoded into behavior;
- registries mirroring concrete types;
- repeated `hasproperty`, `getfield`, or reflection used as semantic dispatch;
- exception handling used to discover protocol support.

### Protocol drift

- optional hooks exist only by being absent;
- required hooks have silent fallbacks;
- generic consumers bypass exported semantic methods;
- every consumer invents its own selectors or labels;
- stage order is duplicated;
- nested local functions or closures hide intended extension points;
- `Vector{Function}` becomes a homemade method table.

### Definition drift

- definitions execute;
- definitions acquire mutable runtime state without owning a lifecycle;
- one generic definition type accumulates all possible fields;
- configuration data and materialized results share one object.

### Abstraction drift

- manager/factory/provider wrappers forward unchanged arguments;
- contexts become dictionaries of unrelated state;
- helpers exist only to hide the orchestrator;
- speculative plugin frameworks replace direct dispatch;
- compatibility aliases preserve unreleased mistakes.

---

## 17. Adoption procedure for an existing subsystem

### Step 1: inventory reality

Record:

- current public entry points;
- current owner(s);
- current result(s);
- current stage sequences;
- current type/symbol/mode decision points;
- current direct field consumers;
- current tests and baselines.

### Step 2: state the preservation contract

Separate:

- semantics and results that must remain;
- accidental API or architecture that may be removed;
- deliberate future refinements that are not part of convergence.

### Step 3: choose the single owner and result

Do this before moving code. Ownership debates postponed until implementation become module-shuffling theater.

### Step 4: write the protocol card

Classify every hook as required, optional, derived, or boundary normalization.

### Step 5: write the orchestrator first

Express only the fixed ordered sequence. Use existing kernels behind stage methods. Do not redesign physics while recovering choreography.

### Step 6: add explicit defaults

Add identity/no-op methods only for legitimate optional semantics.

### Step 7: move variation to methods

Replace central mode/key branches with methods on concrete definitions, rules, observables, backends, or formulations.

### Step 8: establish one result-access protocol

Migrate cross-module consumers to observables or another exported semantic interface. Delete alternate selector grammars after cutover.

### Step 9: add conformance tests

Prove order, entitlement, totality, extension locality, result ownership, type stability, and preserved numerical behavior.

### Step 10: delete shadow machinery

Remove old orchestrators, compatibility wrappers without consumers, unused modes, registries, duplicated accessors, stale docs, and tests that preserve superseded architecture.

---

## 18. Review template

Use this during design or PR review.

```text
Subsystem:
Action:
Owner:
Owned result:

Current orchestrators:
Intended single orchestrator:

Fixed stage sequence:
1.
2.
3.

Required hooks:
- 

Optional hooks and explicit defaults:
- 

Derived hooks:
- 

Dispatch axes:
- 

Boundary normalization:
- 

Unsupported-operation boundary:
- 

Semantic result protocol:
- 

Cross-module direct field access to remove:
- 

Mode/style/key/registry branches to remove:
- 

Normal extension example:
- files/methods added:
- existing files that must not change:

Tests:
- choreography:
- entitlement:
- defaults:
- extension locality:
- result ownership:
- observables:
- type stability:
- numerical/integration baseline:
```

### Acceptance questions

1. Can the public action be found without searching for internal helpers?
2. Can its stage order be read in one place?
3. Does each stage have one owner and one semantic name?
4. Can a supported new type be added without changing the orchestrator?
5. Are optional stages explicit no-ops rather than missing methods?
6. Are required stages incapable of silently succeeding through a fallback?
7. Are symbols/strings normalized once at the boundary?
8. Does the action return the owner’s completed result?
9. Do generic consumers use one semantic result protocol?
10. Are definitions passive?
11. Are contexts concrete and narrowly scoped?
12. Do tests prove the architecture rather than merely exercise the current implementation?
13. Is the resulting implementation smaller in conceptual machinery, even if a few explicit methods were added?

---

## 19. Suggested subsystem mappings

These are initial playbook applications, not declarations that every current implementation already conforms.

| Subsystem | Public action | Definition/dispatch axes | Fixed choreography | Owned result/protocol |
|---|---|---|---|---|
| PlotBuilder | `plot` | plot definition, source type, backend | entitlement → observables → target → panels → series → draw → legend → controls → finalize | render artifact; data via observables |
| DataEntry | `enter` | entry definition, raw source type | parse → normalize → validate → construct | domain object |
| Validation | `validate` | entry type, rule type, handler type | obtain rules → evaluate in order → handle issues → finish | validated entry or report |
| ErrorHandler | `handle!` / `finish` | issue type, handler type | receive issue → react/accumulate → finalize | thrown error, report, log/UI state |
| UnitHandler | `render_quantity` | quantity descriptor, unit dimension | native unit → display unit → convert → format | rendered/scaled quantity |
| Observables | `observe` | result type, observable descriptor | entitlement → extract → attach metadata/reduction as needed | semantic value |
| Export | `export_result` | export definition, backend, source type | observables → tabulate → encode → write → finalize | export artifact |
| ParametricBuilder | package-specific | definition/gridspace types | enumerate → materialize input → call owner action → collect owned results | deterministic result collection |
| UQ | package-specific | sampling/propagation definition | sample/propagate → call owner action → reduce through observables | UQ result/report |
| Computation, later | `compute` | problem, formulation | normalize → check → workspace → assemble → reduce → materialize | fully resolved line parameters |

---

## 20. Seed stubs

The companion file `dispatch_template_method_seeds.jl` contains syntax-level seeds for:

1. a generic dispatch-driven Template Method;
2. validation rules and ErrorHandler dispatch;
3. DataEntry orchestration;
4. typed observables;
5. UnitHandler quantities and conversion;
6. PlotBuilder materialization;
7. export pipelines;
8. a reserved computation pipeline.

These are **seeds, not a framework dependency**. Copy only the relevant shape, rename every stage into domain language, and delete participants that do not own a real responsibility.

```julia
# Dispatch-driven Template Method seed protocols for Julia.
#
# These modules are deliberately small. They demonstrate ownership, fixed
# choreography, typed extension points, explicit defaults, and result ownership.
# Rename every generic stage to the vocabulary of the subsystem that adopts it.

module DispatchTemplateSeed

export AbstractDefinition, AbstractInput, AbstractContext, AbstractResult,
       NoContext, supports, normalize_input, check_input, initialize_context,
       prepare_execution, perform, postprocess, materialize, run

abstract type AbstractDefinition end
abstract type AbstractInput end
abstract type AbstractContext end
abstract type AbstractResult end

struct NoContext <: AbstractContext end

supports(::Type{<:AbstractDefinition}, ::Type{<:AbstractInput}) = false

normalize_input(::AbstractDefinition, input::AbstractInput) = input
check_input(::AbstractDefinition, input::AbstractInput) = input
initialize_context(::AbstractDefinition, ::AbstractInput) = NoContext()
prepare_execution(
    ::AbstractDefinition,
    input::AbstractInput,
    context::AbstractContext,
) = (input, context)

function perform end

postprocess(::AbstractDefinition, raw, ::AbstractContext) = raw

function materialize end

function run(definition::D, input::I) where {
    D<:AbstractDefinition,
    I<:AbstractInput,
}
    supports(D, I) || throw(ArgumentError(
        "$(D) does not support $(I)",
    ))

    normalized = normalize_input(definition, input)
    checked = check_input(definition, normalized)
    context = initialize_context(definition, checked)
    prepared, context = prepare_execution(definition, checked, context)
    raw = perform(definition, prepared, context)
    processed = postprocess(definition, raw, context)
    return materialize(definition, processed, context)
end

end # module DispatchTemplateSeed


module ValidationSeed

export AbstractDataEntry, AbstractRule, AbstractErrorHandler,
       ValidationIssue, ValidationReport, ThrowingHandler, CollectingHandler,
       rules, check, handle!, applyrules, finish, validate,
       Nonnegative, Positive, LessThan, CableGeometryEntry

abstract type AbstractDataEntry end
abstract type AbstractRule end
abstract type AbstractErrorHandler end

struct ValidationIssue
    code::Symbol
    message::String
    context::NamedTuple
end

struct ValidationReport{E}
    entry::E
    issues::Vector{ValidationIssue}
end

struct ThrowingHandler <: AbstractErrorHandler end

mutable struct CollectingHandler <: AbstractErrorHandler
    issues::Vector{ValidationIssue}
end

CollectingHandler() = CollectingHandler(ValidationIssue[])

rules(::Type{<:AbstractDataEntry}) = ()

function check end

handle!(::ThrowingHandler, issue::ValidationIssue) =
    throw(ArgumentError("$(issue.code): $(issue.message)"))

function handle!(handler::CollectingHandler, issue::ValidationIssue)
    push!(handler.issues, issue)
    return handler
end

applyrules(::Tuple{}, ::AbstractDataEntry, handler::AbstractErrorHandler) = handler

function applyrules(
    rule_set::Tuple,
    entry::AbstractDataEntry,
    handler::AbstractErrorHandler,
)
    issue = check(first(rule_set), entry)
    issue === nothing || handle!(handler, issue)
    return applyrules(Base.tail(rule_set), entry, handler)
end

finish(::ThrowingHandler, entry::AbstractDataEntry) = entry
finish(handler::CollectingHandler, entry::AbstractDataEntry) =
    ValidationReport(entry, copy(handler.issues))

function validate(
    entry::AbstractDataEntry,
    handler::AbstractErrorHandler = ThrowingHandler(),
)
    resolved = applyrules(rules(typeof(entry)), entry, handler)
    return finish(resolved, entry)
end

struct Nonnegative{Field} <: AbstractRule end
struct Positive{Field} <: AbstractRule end
struct LessThan{Left,Right} <: AbstractRule end

function check(::Nonnegative{Field}, entry::AbstractDataEntry) where {Field}
    value = getproperty(entry, Field)
    value >= zero(value) && return nothing
    return ValidationIssue(
        :nonnegative,
        "$(Field) must be nonnegative",
        (; field = Field, value),
    )
end

function check(::Positive{Field}, entry::AbstractDataEntry) where {Field}
    value = getproperty(entry, Field)
    value > zero(value) && return nothing
    return ValidationIssue(
        :positive,
        "$(Field) must be positive",
        (; field = Field, value),
    )
end

function check(::LessThan{Left,Right}, entry::AbstractDataEntry) where {Left,Right}
    left = getproperty(entry, Left)
    right = getproperty(entry, Right)
    left < right && return nothing
    return ValidationIssue(
        :ordering,
        "$(Left) must be less than $(Right)",
        (; left_field = Left, left, right_field = Right, right),
    )
end

struct CableGeometryEntry{T} <: AbstractDataEntry
    r_in::T
    r_ex::T
end

rules(::Type{<:CableGeometryEntry}) = (
    Nonnegative{:r_in}(),
    Positive{:r_ex}(),
    LessThan{:r_in,:r_ex}(),
)

end # module ValidationSeed


module DataEntrySeed

using ..ValidationSeed

export AbstractEntryDefinition, AbstractRawEntry, AbstractOwnedObject,
       parse_entry, normalize_entry, construct_entry, enter

abstract type AbstractEntryDefinition end
abstract type AbstractRawEntry end
abstract type AbstractOwnedObject end

function parse_entry end

normalize_entry(::AbstractEntryDefinition, entry::AbstractDataEntry) = entry

function construct_entry end

function enter(
    definition::AbstractEntryDefinition,
    raw::AbstractRawEntry,
)
    parsed = parse_entry(definition, raw)
    normalized = normalize_entry(definition, parsed)
    accepted = validate(normalized)
    return construct_entry(definition, accepted)
end

end # module DataEntrySeed


module ObservableGrammarSeed

export AbstractObservable, AbstractQuantity, NoQuantity,
       available_observables, observe, observable, observable_label, quantity,
       observable_axes, FrequencyObservable, SeriesImpedanceObservable,
       ShuntAdmittanceObservable

abstract type AbstractObservable end
abstract type AbstractQuantity end

struct NoQuantity <: AbstractQuantity end
struct FrequencyObservable <: AbstractObservable end
struct SeriesImpedanceObservable <: AbstractObservable end
struct ShuntAdmittanceObservable <: AbstractObservable end

available_observables(::Type) = ()

function observe end

observable_label(observable::AbstractObservable) = String(nameof(typeof(observable)))
quantity(::AbstractObservable) = NoQuantity()
observable_axes(::AbstractObservable) = ()

# User-facing symbolic names may be normalized once at the API boundary.
# Internal consumers should carry the typed descriptor returned here.
observable(::Val{:frequency}) = FrequencyObservable()
observable(::Val{:series_impedance}) = SeriesImpedanceObservable()
observable(::Val{:shunt_admittance}) = ShuntAdmittanceObservable()

end # module ObservableGrammarSeed


module UnitHandlerSeed

using ..ObservableGrammarSeed: AbstractQuantity

export Unit, native_unit, display_unit, quantity_label, quantity_symbol,
       convert_value, format_quantity, render_quantity,
       FrequencyQuantity, SeriesResistanceQuantity

struct Unit{Dimension,T}
    symbol::String
    to_si::T
end

struct FrequencyQuantity <: AbstractQuantity end
struct SeriesResistanceQuantity <: AbstractQuantity end

function native_unit end

native_unit(::FrequencyQuantity) = Unit{:frequency}("Hz", 1.0)
native_unit(::SeriesResistanceQuantity) = Unit{:series_resistance}("Ω/m", 1.0)

display_unit(quantity::AbstractQuantity) = native_unit(quantity)
display_unit(::SeriesResistanceQuantity) =
    Unit{:series_resistance}("Ω/km", 1.0e-3)

quantity_label(quantity::AbstractQuantity) = String(nameof(typeof(quantity)))
quantity_label(::FrequencyQuantity) = "Frequency"
quantity_label(::SeriesResistanceQuantity) = "Series resistance"

quantity_symbol(quantity::AbstractQuantity) = quantity_label(quantity)
quantity_symbol(::FrequencyQuantity) = "f"
quantity_symbol(::SeriesResistanceQuantity) = "R"

function convert_value(value, from::Unit{Dimension}, to::Unit{Dimension}) where {Dimension}
    return value * from.to_si / to.to_si
end

function format_quantity(value, quantity::AbstractQuantity, unit::Unit)
    return string(quantity_symbol(quantity), " = ", value, " ", unit.symbol)
end

function render_quantity(value, quantity::AbstractQuantity)
    from = native_unit(quantity)
    to = display_unit(quantity)
    converted = convert_value(value, from, to)
    return format_quantity(converted, quantity, to)
end

end # module UnitHandlerSeed


module PlotBuilderSeed

using ..ObservableGrammarSeed

export AbstractPlotDefinition, AbstractPlotBackend, PlotArtifact,
       supports_plot, observable_requests, panel_definitions,
       series_definitions, create_target, create_panels, draw_series!,
       place_legend!, attach_controls!, finalize_plot, plot

abstract type AbstractPlotDefinition end
abstract type AbstractPlotBackend end

struct PlotArtifact{Target,Panels}
    target::Target
    panels::Panels
end

supports_plot(::Type{<:AbstractPlotDefinition}, ::Type) = false
observable_requests(::AbstractPlotDefinition) = ()
panel_definitions(::AbstractPlotDefinition) = ()
series_definitions(::AbstractPlotDefinition, data::Tuple) = data

struct ObserveFrom{Source}
    source::Source
end

(observer::ObserveFrom)(observable::AbstractObservable) =
    observe(observer.source, observable)

collect_observables(source, requests::Tuple) = map(ObserveFrom(source), requests)

function create_target end
function create_panels end
function draw_series! end

place_legend!(
    ::AbstractPlotBackend,
    target,
    panels,
    ::AbstractPlotDefinition,
) = nothing

attach_controls!(
    ::AbstractPlotBackend,
    target,
    panels,
    ::AbstractPlotDefinition,
) = nothing

finalize_plot(
    ::AbstractPlotBackend,
    target,
    panels,
    ::AbstractPlotDefinition,
) = PlotArtifact(target, panels)

function plot(
    definition::D,
    source,
    backend::B,
) where {D<:AbstractPlotDefinition,B<:AbstractPlotBackend}
    supports_plot(D, typeof(source)) || throw(ArgumentError(
        "$(D) cannot plot $(typeof(source))",
    ))

    requests = observable_requests(definition)
    data = collect_observables(source, requests)
    target = create_target(backend, definition)
    panels = create_panels(backend, target, panel_definitions(definition))
    series = series_definitions(definition, data)
    draw_series!(backend, panels, series, data, definition)
    place_legend!(backend, target, panels, definition)
    attach_controls!(backend, target, panels, definition)
    return finalize_plot(backend, target, panels, definition)
end

end # module PlotBuilderSeed


module ExportPipelineSeed

using ..ObservableGrammarSeed

export AbstractExportDefinition, AbstractExportBackend, ExportArtifact,
       supports_export, observable_requests, tabulate, encode,
       write_export, finalize_export, export_result

abstract type AbstractExportDefinition end
abstract type AbstractExportBackend end

struct ExportArtifact{Location,Metadata}
    location::Location
    metadata::Metadata
end

supports_export(::Type{<:AbstractExportDefinition}, ::Type) = false
observable_requests(::AbstractExportDefinition) = ()

struct ObserveFrom{Source}
    source::Source
end

(observer::ObserveFrom)(observable::AbstractObservable) =
    observe(observer.source, observable)

collect_observables(source, requests::Tuple) = map(ObserveFrom(source), requests)

function tabulate end
function encode end
function write_export end

finalize_export(
    ::AbstractExportBackend,
    location,
    ::AbstractExportDefinition,
) = ExportArtifact(location, NamedTuple())

function export_result(
    definition::D,
    source,
    backend::B,
) where {D<:AbstractExportDefinition,B<:AbstractExportBackend}
    supports_export(D, typeof(source)) || throw(ArgumentError(
        "$(D) cannot export $(typeof(source))",
    ))

    data = collect_observables(source, observable_requests(definition))
    table = tabulate(definition, data)
    payload = encode(backend, table, definition)
    location = write_export(backend, payload, definition)
    return finalize_export(backend, location, definition)
end

end # module ExportPipelineSeed


module ComputationPipelineSeed

export AbstractProblem, AbstractFormulation, AbstractWorkspace,
       AbstractComputedResult, normalize_problem, check_problem,
       initialize_workspace, assemble!, reduce_system, materialize_result,
       compute

abstract type AbstractProblem end
abstract type AbstractFormulation end
abstract type AbstractWorkspace end
abstract type AbstractComputedResult end

normalize_problem(::AbstractFormulation, problem::AbstractProblem) = problem
check_problem(::AbstractFormulation, problem::AbstractProblem) = problem

function initialize_workspace end
function assemble! end

reduce_system(
    ::AbstractFormulation,
    workspace::AbstractWorkspace,
) = workspace

function materialize_result end

function compute(
    problem::AbstractProblem,
    formulation::AbstractFormulation,
)
    normalized = normalize_problem(formulation, problem)
    checked = check_problem(formulation, normalized)
    workspace = initialize_workspace(formulation, checked)
    assemble!(workspace, formulation, checked)
    reduced = reduce_system(formulation, workspace)
    return materialize_result(formulation, reduced, checked)
end

end # module ComputationPipelineSeed
```

---

## 21. References and consultation map

### Foundational pattern

1. **Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides. _Design Patterns: Elements of Reusable Object-Oriented Software_. Addison-Wesley, 1994/1995.** Consult the behavioral-pattern chapter for Template Method and Hook Method. ISBN `978-0-201-63361-0`; ACM bibliographic DOI `10.5555/186897`.

### Julia language references

2. **Julia Manual: Methods.** Consult for generic functions, method selection, multiple dispatch, empty generic functions, method ambiguities, and dispatch-oriented design patterns.
3. **Julia Manual: Interfaces.** Consult for the model in which a small set of required methods defines an informal interface and enables generic derived behavior.
4. **Julia Manual: Style Guide.** Consult especially “Prefer exported methods over direct field access,” mutation naming with `!`, argument normalization at caller boundaries, and avoiding unnecessary macros/static parameters.
5. **Julia Manual: Performance Tips.** Consult for type stability, concrete fields, specialization, function barriers, captured variables, values-as-parameters, and the warning against abusing dispatch for large runtime taxonomies.
6. **Julia Manual: Constructors.** Consult when definitions or materialized result types require outer-constructor normalization without putting logic into dumb core structs.

### Mature Julia interface case studies

7. **Tables.jl documentation: implementing and consuming the Tables interface.** A strong example of a small informal interface supporting many producers and consumers without a central table-class hierarchy.
8. **CommonSolve.jl documentation and SciML common-interface documentation.** A useful case study in one common action (`solve`, `init`, `solve!`, `step!`) extended by problem and algorithm types through dispatch. Consult the architecture, not every SciML layer.
9. **Makie documentation: Recipes and conversion pipeline.** Consult for typed plot extension, `convert_arguments`, recipes, and backend-independent plotting methods. Use as a case study, not as permission to duplicate Makie inside PlotBuilder.
10. **Julia Base collection interfaces.** Iteration, indexing, broadcasting, and array behavior demonstrate required hooks, optional methods, derived generic behavior, and traits such as index style.

### Optional trait reference

11. **SimpleTraits.jl documentation and the Tim Holy trait-dispatch literature.** Consult only when behavior cuts orthogonally across an existing hierarchy. Ordinary multiple dispatch remains the default.

### Retrieval locations

- Julia Manual, Methods: <https://docs.julialang.org/en/v1/manual/methods/>
- Julia Manual, Interfaces: <https://docs.julialang.org/en/v1/manual/interfaces/>
- Julia Manual, Style Guide: <https://docs.julialang.org/en/v1/manual/style-guide/>
- Julia Manual, Performance Tips: <https://docs.julialang.org/en/v1/manual/performance-tips/>
- Julia Manual, Constructors: <https://docs.julialang.org/en/v1/manual/constructors/>
- Tables.jl interface documentation: <https://tables.juliadata.org/stable/>
- CommonSolve.jl: <https://docs.sciml.ai/CommonSolve/>
- SciML common-interface developer documentation: <https://docs.sciml.ai/SciMLBase/dev/>
- Makie recipes: <https://docs.makie.org/stable/explanations/recipes>
- SimpleTraits.jl: <https://github.com/mauro3/SimpleTraits.jl>
- Pearson record for _Design Patterns_: <https://www.pearson.com/en-us/subject-catalog/p/design-patterns-elements-of-reusable-object-oriented-software/P200000009480>
- ACM bibliographic record: <https://dl.acm.org/doi/10.5555/186897>

---

## 22. Compact normative form

Use this paragraph in repository instructions, architecture documents, or planning prompts:

> Extensible first-class actions shall use a dispatch-driven Template Method. Each action has one owning module, one public orchestrator, one owned result, and one explicit ordered sequence of atomic stage methods. Concrete behavior is introduced through multiple dispatch on domain types, definitions, rules, backends, formulations, or typed descriptors. The interface is total over its admitted domain: required stages exist for every supported combination, optional stages have explicit identity/no-op methods, and unsupported combinations fail at the entitlement boundary before partial execution. Declarative definitions capture intent but do not execute. Cross-module consumers read owned results through one exported semantic protocol. Adding a supported type normally adds local methods and tests without editing the orchestrator, introducing a parallel pipeline, or extending a central `mode`, `style`, key, registry, or type-inspection switch.

That is the entire doctrine. The rest of the playbook exists because software agents can turn one paragraph into seventeen mutually recursive managers when left unsupervised.
