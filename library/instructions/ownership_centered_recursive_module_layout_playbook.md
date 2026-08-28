# Ownership-Centered Recursive Module Layout Playbook

> **Group by owner first. Split by responsibility second. Recurse only when the owned concept has earned more structure.**

## Status

This document defines a repository-scaffolding policy for Julia packages whose extensibility is primarily expressed through multiple dispatch and stable orchestration methods.

The policy name used here is **Ownership-Centered Recursive Module Layout**.

That exact phrase is a project convention, not an established industry pattern. The design is a composition of documented ideas:

- **information-hiding decomposition**: group code around decisions and concepts that one owner controls;
- **package-by-feature or package-by-component**: organize the source tree around functional owners rather than global folders such as `types`, `services`, or `handlers`;
- **Common Closure Principle**: code that changes for the same reason should remain together;
- **locality of behavior and colocation**: keep declarations, policies, and methods near the concepts they explain;
- **recursive decomposition**: apply the same rules again when an owned concept grows into a subsystem;
- **protocol-oriented source files**: name files after the methods, interfaces, and language protocols they implement.

The closest compact description in established vocabulary is:

> **Package-by-feature with local protocol-oriented layering and recursive decomposition.**

This is not vertical-slice architecture, layered architecture, hexagonal architecture, or a modular-monolith recipe. Those terms describe different concerns. This playbook concerns where Julia source code lives, how ownership is made visible, and how a repository grows without turning into a taxonomy museum.

---

## 1. The organizing law

Every source artifact must answer two questions:

1. **Who owns this concept or behavior?**
2. **What responsibility does this file perform for that owner?**

The first answer determines the directory.

The second answer determines the file.

The resulting rule is:

```text
owner / responsibility
```

Examples:

```text
plotbuilder/definitions.jl
plotbuilder/plot.jl
validation/rules.jl
validation/validate.jl
engine/lineparameters.jl
engine/observables.jl
cablebuilder/cabledesign/stack.jl
```

A directory is not created merely because several files share a suffix. A file is not moved to a global bucket merely because it overloads the same external function as another unrelated feature.

### 1.1 Owner first

An owner is a module, subsystem, domain concept, or first-class action with a coherent responsibility.

Valid owners include:

- `PlotBuilder`;
- `Validation`;
- `UnitHandler`;
- `Engine`;
- `CableDesign`;
- `LineParameters`;
- `Observables` when it is a real shared grammar;
- a concrete import/export subsystem;
- a formulation family;
- a package extension.

Invalid pseudo-owners include:

- `helpers`;
- `utils`;
- `misc`;
- `common` without a precise shared contract;
- `managers`;
- `handlers` when the word merely hides unrelated actions;
- `implementations`;
- `services` in a scientific library with no service concept.

### 1.2 Responsibility second

Within an owner, files are named after the semantic responsibility they implement:

- `types.jl`;
- `interfaces.jl`;
- `definitions.jl`;
- `constructors.jl`;
- `validate.jl`;
- `plot.jl`;
- `observables.jl`;
- `iteration.jl`;
- `indexing.jl`;
- `base.jl`;
- `tables.jl`;
- `dataframe.jl`;
- `show.jl`;
- `serialize.jl`;
- a named algorithm such as `kronreduce.jl`;
- an owned concept such as `cabledesign.jl`.

A responsibility filename is not a license to collect unrelated code. `base.jl` contains methods extending `Base`; it is not a polite alias for `misc.jl`.

---

## 2. Julia-specific premise: files, directories, and modules are independent

Julia does not map files or directories to modules. `include` evaluates a file in the global scope of the including module. A module can span many files, one file can contain several modules, and a directory has no language meaning by itself.

Therefore treat the following as separate decisions:

| Artifact | What it provides | Cost introduced |
|---|---|---|
| File | Reading and editing unit | Include ordering and navigation |
| Directory | Ownership and navigation grouping | One more level in the tree |
| Julia `module` | Namespace, global scope, explicit imports/exports | Qualification, import wiring, separate method visibility |
| Package | Release, dependency, version, and loading unit | Independent metadata and compatibility obligations |

The default growth sequence is:

```text
file → directory inside the existing module → submodule → separate package
```

Do not skip directly from “this file is large” to “this needs a submodule.” A directory is the cheap organizational tool. A Julia submodule is a semantic namespace and dependency decision.

### 2.1 A folder does not imply a submodule

This is valid and often preferable:

```text
src/
  MyPackage.jl
  engine/
    lineparameters/
      lineparameters.jl
      constructors.jl
      observables.jl
```

All three files may still be included into one `Engine` module.

Use a submodule only when the concept needs at least one of the following:

- a distinct namespace;
- a separately stated public interface;
- dependency isolation;
- a coherent set of imports that should not leak into the parent;
- an independently understandable subsystem;
- name collision control;
- optional loading through a package extension;
- ownership strong enough that callers should qualify it.

### 2.2 A submodule does not need a large hierarchy

A small but semantically independent subsystem may deserve a submodule even if its code is short. Line count is not the criterion. Ownership is.

### 2.3 One package module remains normal Julia

Large Julia packages commonly use one top-level package module and several feature directories whose files are included directly into it. DataFrames.jl, for example, groups code under directories such as `abstractdataframe`, `dataframe`, `groupeddataframe`, and `join` while retaining one `DataFrames` module.

Submodules are available and useful, but they are not the default substitute for source directories.

---

## 3. Repository-level scaffold

A package repository should start from the Julia package layout and add only directories with a real lifecycle.

```text
PackageName.jl/
├── Project.toml
├── src/
│   └── PackageName.jl
├── ext/                 # optional package integrations
├── test/
│   └── runtests.jl
├── docs/                # maintained package documentation
├── benchmark/           # reproducible performance work
├── examples/            # executable user-facing examples
├── scripts/             # repository maintenance, not library logic
└── dev/                 # local experiments and development environments
```

Only `Project.toml` and `src/PackageName.jl` are needed for the minimal package. The remaining directories exist when the repository actually uses them.

### 3.1 `src/`

Contains shipped runtime source code.

Do not place the following in `src/`:

- exploratory scripts;
- one-off migrations;
- benchmark drivers;
- test fixtures;
- generated reports;
- local debugging programs;
- abandoned prototypes kept for emotional support.

### 3.2 `ext/`

Contains Julia package extensions for optional dependencies.

Use this when functionality requires a package that should not be loaded or installed for every user. Plotting backends, DataFrames integration, Gmsh integration, or another heavyweight adapter often belong here.

### 3.3 `test/`

Contains contract, numerical, integration, and regression tests. `test/runtests.jl` remains the package entry point.

Mirror source ownership loosely, not mechanically:

```text
test/
├── runtests.jl
├── engine/
├── plotbuilder/
├── validation/
└── extensions/
```

Tests are grouped by behavior and contract. There is no requirement for one test file per source file, because that ritual mostly tests the patience of maintainers.

### 3.4 `benchmark/`

Contains reproducible benchmark code and its environment. Benchmark implementation does not belong beside hot-path source merely because it measures it.

### 3.5 `examples/`

Contains complete supported usage examples. Minimal examples used only by documentation may instead live under the documentation system.

### 3.6 `scripts/`

Contains repository operations such as data generation, release preparation, or deterministic conversion tasks. Library methods called by scripts still belong under their actual source owner.

### 3.7 `dev/`

Contains experiments, diagnostics, and development-only environments that should not participate in package loading.

Work in progress that already belongs to the runtime architecture stays under its owner in `src/`. Experimental junk with no supported runtime role does not.

---

## 4. The package entry file

`src/PackageName.jl` is the package index and assembly point.

It should make the package structure readable without opening forty files.

Its responsibilities are limited to:

1. declaring the package module;
2. declaring package dependencies;
3. declaring public and exported names;
4. including root contracts and child module entry files;
5. importing or reexporting selected child names;
6. defining `__init__` only when runtime initialization is genuinely required.

It should not contain substantial domain algorithms.

### 4.1 Seed stub

```julia
module PackageName

using LinearAlgebra

export compute, validate, plot
public AbstractDefinition, observables

include("interfaces.jl")
include("types.jl")

include("grammar/Grammar.jl")
include("engine/Engine.jl")
include("validation/Validation.jl")
include("plotbuilder/PlotBuilder.jl")

using .Engine: LineParameters, compute
using .Validation: validate
using .PlotBuilder: plot

end # module PackageName
```

Use `public` only when the supported Julia version includes it. Otherwise document non-exported public names explicitly.

### 4.2 Root source files

Root files are permitted for concepts genuinely shared by multiple sibling owners and not naturally owned by one of them.

Typical root files are:

```text
interfaces.jl
abstracttypes.jl
domains.jl
constants.jl
```

A root concept must pass the **two-owner test**:

> At least two independent child owners use this concept, and placing it in either child would invert or distort ownership.

Failure of that test means the concept belongs inside its actual owner.

Do not create root-level `utils.jl`, `common.jl`, or `helpers.jl`. Those files are where ownership goes to be quietly murdered.

---

## 5. The module-directory grammar

A substantial owned module receives a directory and one entry file named after the module.

Project convention:

```text
src/
  plotbuilder/
    PlotBuilder.jl
```

The directory name is lowercase. The module entry filename matches the Julia module identifier exactly.

A module directory may contain:

```text
plotbuilder/
├── PlotBuilder.jl
├── types.jl
├── interfaces.jl
├── definitions.jl
├── plot.jl
├── observables.jl
├── base.jl
├── lineparameters.jl
└── panels/
    ├── panels.jl
    ├── layout.jl
    └── legend.jl
```

This is a vocabulary, not a mandatory empty scaffold. Create only the files the module needs.

### 5.1 Module entry contract

`Module.jl` should contain:

1. `module ModuleName`;
2. dependencies and imports;
3. `export` and `public` declarations;
4. `include` statements in semantic dependency order;
5. child-submodule imports or reexports;
6. `end`.

It should not become the implementation monolith it was supposed to index.

### 5.2 Module entry seed

```julia
module PlotBuilder

import ..Grammar: observables, observe
import Base: show

export plot, AbstractPlotDefinition
public render, entitled

include("types.jl")
include("interfaces.jl")
include("definitions.jl")
include("plot.jl")
include("base.jl")

end # module PlotBuilder
```

### 5.3 Include order

Include files by semantic dependency, normally:

```text
abstract contracts
→ concrete types
→ outer constructors and normalization
→ interface defaults
→ owned concepts
→ algorithms and orchestrators
→ protocol implementations
→ display and serialization
→ precompile workload
```

The exact order may differ, but it must be explainable.

If include order requires circular tricks, repeated forward declarations, or dynamic injection, the source tree is exposing a dependency cycle rather than solving one.

---

## 6. Standard file roles

### 6.1 `types.jl`

Contains module-wide abstract and concrete data types.

Use it when several files need the types and no narrower owner is clearer.

Do not put all package types in one root `types.jl`. A type belongs with the subsystem that owns its invariants.

Structs with extensive behavior may receive their own file or directory.

### 6.2 `interfaces.jl`

Contains generic-function declarations and the smallest shared contracts owned by the module.

Examples:

```julia
function observables end
function prepare end
function materialize end
```

It may also contain explicit fallback, identity, or rejection methods that are part of a total informal interface.

It must not contain arbitrary methods merely because they are “generic.”

### 6.3 `definitions.jl`

Contains passive declarative objects that configure the module’s actions.

Concrete definitions stay close to the action and owned object they configure. A definition used only by one plot family belongs beside that plot family, not in a package-wide registry of every noun ending in `Definition`.

### 6.4 `constructors.jl`

Contains substantial outer constructors, normalization, promotion, and conversion needed to create owned objects.

Small obvious constructors remain with the type. Split only when constructor logic becomes an independent reading unit.

### 6.5 `<action>.jl`

Contains one first-class action and its fixed choreography:

```text
compute.jl
validate.jl
plot.jl
export.jl
stack.jl
reduce.jl
```

Name the file after the actual public action. Do not use `orchestrator.jl`, `pipeline.jl`, or `runner.jl` when a precise domain verb exists.

### 6.6 `<ownedobject>.jl`

Contains one central owned concept and the tightly coupled methods required to understand it.

Example:

```text
cabledesign.jl
lineparameters.jl
material.jl
```

Promote it to a directory when its constructors, protocols, algorithms, or subtype families no longer fit one coherent file.

### 6.7 `base.jl`

Contains methods extending `Base` or `Core` for types owned by the module.

Typical methods include:

```text
show
iterate
length
size
getindex
setindex!
convert
promote_rule
eltype
broadcastable
```

When one Base protocol becomes substantial, split it into a precise file such as `iteration.jl`, `indexing.jl`, or `show.jl`.

`base.jl` must not contain ordinary package functions.

### 6.8 `tables.jl`

Contains a Tables.jl interface or other table protocol owned by the module.

Use this when the object genuinely has table semantics. Do not manufacture a table interface solely to feed one plotting function.

### 6.9 `dataframe.jl`

Contains DataFrames-specific methods only when DataFrames is an unconditional package dependency.

If DataFrames is optional, the integration belongs under `ext/`.

### 6.10 `plot.jl`

Contains the package-owned plotting action or methods for an unconditional plotting dependency.

If Makie, Plots, or another backend is optional, backend-specific methods belong in a package extension. The core package may still own backend-neutral plot definitions and rendering grammar.

### 6.11 `observables.jl`

Contains the semantic read protocol for owned results when that protocol is substantial enough to deserve a file.

It should define how generic consumers discover and extract supported quantities. It should not duplicate direct accessors under a more fashionable name.

### 6.12 `errors.jl`

Contains owned exception types and error-reporting data with stable semantics.

It does not contain every `throw` in the module, nor does it become a universal ErrorHandler bureaucracy.

### 6.13 Algorithm files

A complex algorithm may receive a dedicated file even when it is used by one public action.

The filename names the algorithm or physical operation:

```text
kronreduce.jl
modaltransform.jl
earthreturn.jl
strandpacking.jl
```

This is justified by human and agent navigation, independent testing, or mathematical coherence. It is not justified by a desire to make every file equally small.

---

## 7. Method-placement rule

Julia methods often belong simultaneously to a type, an action, and a generic function. Use the reason for change to place them.

### 7.1 Place by the thing that owns the policy

Use this deterministic rule:

| A method changes because… | Place it with… |
|---|---|
| the owned object’s semantics changed | the owned object |
| the action’s choreography or policy changed | the action file |
| a language protocol changed | `base.jl`, `iteration.jl`, `indexing.jl`, or another protocol file |
| an optional external package changed | the package extension |
| a declarative definition changed | the definition or its family |
| a shared result-read contract changed | `observables.jl` or its owning grammar |

### 7.2 Action-owned overload families

A file such as `plot.jl` may contain all methods that define the module-owned `plot` action when those methods jointly express plotting policy.

Do not create a generic `overloads.jl`. Name the file after the call being extended.

### 7.3 Type-owned hook methods

Template Method hooks that explain one concrete definition or type remain near that type:

```julia
panels(::FrequencyPlotDefinition, source) = ...
legend(::FrequencyPlotDefinition) = ...
layout(::FrequencyPlotDefinition) = ...
```

When all such methods are placed in one distant trait warehouse, the definition becomes a useless data shell and readers must perform code archaeology to understand it.

### 7.4 Integration-owned methods

Methods whose existence depends on another package belong to the integration, not to the domain object.

This prevents the core source tree from acquiring unconditional imports and stale adapter code.

---

## 8. Recursive decomposition

Apply the same owner/responsibility grammar at every level.

### 8.1 Stage 1: one file

```text
engine/
  lineparameters.jl
```

Use while the concept remains coherent and navigable.

### 8.2 Stage 2: owned directory, same parent module

```text
engine/
  lineparameters/
    lineparameters.jl
    constructors.jl
    observables.jl
    dataframe.jl
```

Use when the concept owns several responsibilities but does not need its own namespace.

### 8.3 Stage 3: owned submodule

```text
engine/
  lineparameters/
    LineParameters.jl
    types.jl
    constructors.jl
    observables.jl
    reduce.jl
```

Use only after `LineParameters` has become a separately understandable subsystem with its own imports, interface, and public names.

### 8.4 Stage 4: separate package

Extract only when the subsystem has:

- independent users;
- independent release pressure;
- a dependency set that the parent should not impose;
- a stable public interface;
- independent testing and documentation;
- a reason to version separately.

“Large directory” is not a release strategy.

---

## 9. Submodule decision test

Create a Julia submodule only when all of the following are true:

1. The candidate has a one-sentence responsibility.
2. It owns names or methods that form a coherent interface.
3. Its imports can be stated independently.
4. Parent and sibling code can interact with it through explicit methods rather than shared implementation state.
5. The namespace improves understanding more than it increases qualification and import wiring.

At least one of the following must also be true:

- its public names should be qualified;
- it isolates optional or heavy dependencies;
- it prevents real name collisions;
- it contains a complete feature family;
- it can be tested as a coherent subsystem;
- it may plausibly become a package later.

Do not create a submodule because:

- a type has subtypes;
- a file crossed an arbitrary line count;
- a directory exists;
- an agent suggested “better separation of concerns” without naming the concern;
- imports look untidy;
- private functions need somewhere to hide.

---

## 10. Template Method placement

This repository layout is designed to support dispatch-driven Template Methods without scattering the choreography.

For each extensible action:

```text
owner/
├── interfaces.jl       # hook declarations and defaults
├── definitions.jl      # passive definitions
├── <action>.jl         # one fixed orchestrator
└── <owned types>.jl    # concrete hook methods near their owners
```

Example:

```text
plotbuilder/
├── PlotBuilder.jl
├── types.jl
├── interfaces.jl
├── plot.jl
├── frequencyplot.jl
├── matrixplot.jl
└── distributionplot.jl
```

`plot.jl` contains the fixed sequence:

```julia
function plot(definition::AbstractPlotDefinition, source)
    check_entitlement(definition, source)
    data = fetch_data(definition, source)
    panels = make_panels(definition, data)
    figure = make_figure(definition, panels)
    apply_labels!(definition, figure, data)
    apply_controls!(definition, figure, data)
    return display_figure(definition, figure)
end
```

`frequencyplot.jl` contains methods such as:

```julia
fetch_data(::FrequencyPlotDefinition, source) = ...
make_panels(::FrequencyPlotDefinition, data) = ...
apply_controls!(::FrequencyPlotDefinition, figure, data) = nothing
```

The orchestrator remains in one file. The object-specific declarations remain near the object. Humans can read the action in sequence and inspect one concrete definition without touring the whole package, an achievement apparently considered extravagant by many software projects.

---

## 11. External overload and package-extension policy

Method placement depends on ownership of the function, type, and dependency.

| Function owner | Type owner | Dependency | Location |
|---|---|---|---|
| This package | This package | core | owner module |
| `Base` or stdlib | This package | core | `base.jl` or precise protocol file |
| Hard dependency | This package | unconditional | dedicated integration file under owner |
| This package | Optional dependency | optional | `ext/PackageDependencyExt.jl` |
| Optional dependency | This package | optional | `ext/PackageDependencyExt.jl` |
| Third party A | Third party B | any | do not define; this is type piracy unless an extension contract explicitly owns the interaction |

### 11.1 Extension seed

`Project.toml`:

```toml
[weakdeps]
DataFrames = "a93c6f00-e57d-5684-b7b6-d8193f3e46c0"

[extensions]
PackageNameDataFramesExt = "DataFrames"
```

`ext/PackageNameDataFramesExt.jl`:

```julia
module PackageNameDataFramesExt

using PackageName
import DataFrames

function DataFrames.DataFrame(result::PackageName.LineParameters)
    return DataFrames.DataFrame(PackageName.observables(result))
end

end # module PackageNameDataFramesExt
```

For a complex extension, use:

```text
ext/
  PackageNameMakieExt/
    PackageNameMakieExt.jl
    render.jl
    controls.jl
```

The extension repeats the same owner/responsibility grammar.

### 11.2 Core package rule

The core package owns backend-neutral semantics. An extension owns translation into an optional dependency.

A PlotBuilder may therefore live in `src/`, while concrete Makie window construction lives in `ext/PackageNameMakieExt/`.

---

## 12. Shared interfaces and the root grammar

A shared grammar is justified when several independent modules extend the same semantic calls.

Examples:

```julia
function observables end
function observe end
function validate end
function compute end
```

Place such declarations at the lowest common owner that can legitimately define their meaning.

Do not centralize a generic function merely because many methods exist. The owner is the subsystem that defines the operation’s semantics and result contract.

### 12.1 Root interface test

A root-level interface must satisfy all of the following:

- at least two sibling modules need it;
- neither sibling is the obvious semantic owner;
- the interface has one stable meaning across those modules;
- callers benefit from depending on the parent rather than a concrete child;
- the parent can document the admitted types and behavior.

Otherwise keep the function with its real owner and import it where needed.

### 12.2 No generic dumping module

A `Commons`, `Core`, or `Grammar` module is allowed only when its content is itself a coherent contract.

It must not become the place for:

- types nobody wanted to own;
- dependency-cycle casualties;
- constants used once;
- convenience wrappers;
- “shared” methods with one caller;
- aliases created to avoid fixing imports.

---

## 13. Dependency direction

### 13.1 Parent owns shared contracts

When several child modules implement one contract, the parent or a dedicated grammar owner declares the generic functions and abstract types. Children import and extend them.

### 13.2 Children do not mutate parent namespaces

No runtime namespace injection, `eval`-based registration, or hidden module mutation.

### 13.3 Siblings avoid mutual imports

Sibling modules communicate through:

- parent-owned interfaces;
- explicitly owned result types;
- one directed dependency that reflects real semantics.

Mutual sibling imports usually indicate that the decomposition cut through one concept.

### 13.4 Imports are explicit

Use `import Module: function` when adding methods. Use `using Module: Name` when consuming names without extension.

Do not rely on broad exports to make internal dependency direction invisible.

### 13.5 Module entry files expose the graph

A reader should be able to inspect imports and includes in each `Module.jl` and understand the dependency graph without tracing dynamic loading rituals.

---

## 14. Testing scaffold

The source tree exposes ownership. The test tree verifies contracts owned by that structure.

```text
test/
├── runtests.jl
├── grammar/
│   └── observables.jl
├── engine/
│   ├── lineparameters.jl
│   └── numerical_baselines.jl
├── validation/
│   ├── rules.jl
│   └── orchestration.jl
├── plotbuilder/
│   ├── definitions.jl
│   └── orchestration.jl
└── extensions/
    ├── dataframes.jl
    └── makie.jl
```

### 14.1 Test by contract, not by file

Do not mirror every source file mechanically. Test:

- public behavior;
- interface conformance;
- owned invariants;
- Template Method stage order where order matters;
- explicit no-op hooks;
- unsupported dispatch;
- numerical baselines;
- extension activation and behavior.

### 14.2 Current Julia test environment

For Julia 1.12+, use a workspace with `test/Project.toml` for test-only dependencies. The package test entry remains `test/runtests.jl`.

Benchmarks and documentation environments may also join the workspace when the repository benefits from one resolved dependency graph.

---

## 15. Documentation and agent navigation

This layout is partly a navigation system. Treat that function seriously.

### 15.1 Every module entry is an index

A module entry file should reveal:

- what the module imports;
- what it exports;
- what files it includes;
- what submodules it contains;
- the intended include order.

### 15.2 Every directory has one sentence of ownership

The module docstring or developer guide states:

```text
Owner:
Purpose:
Public actions:
Owned results:
Extension points:
Dependencies:
```

Do not create a `README.md` in every directory by ritual. Add one only when the directory has independently useful explanation that does not belong in module documentation.

### 15.3 Stable filenames are an agent interface

Predictable names such as `types.jl`, `interfaces.jl`, `validate.jl`, and `observables.jl` let humans and code agents locate behavior without semantic guessing.

That benefit disappears if the same filename means different things in every module. File-role definitions in this playbook are therefore part of the architecture, not decoration.

### 15.4 Complex algorithms deserve named files

A dedicated file is justified when it makes mathematical review, debugging, profiling, or code-agent inspection materially easier.

Name the file after the algorithm. Do not exile it to `helpers.jl` because only one caller currently exists.

---

## 16. Growth rules

### 16.1 Create a new file when

- one responsibility can be named precisely;
- the current file mixes independent reasons for change;
- the code forms a coherent algorithm or protocol implementation;
- readers repeatedly need to navigate directly to that behavior;
- the split removes a monolithic reading burden without creating indirection.

### 16.2 Create a new directory when

- an owned concept now has several files;
- those files share one reason for change;
- moving them together makes ownership obvious;
- the directory name is a domain noun or action family, not a technical junk category.

### 16.3 Create a submodule when

- the submodule decision test in Section 9 passes.

### 16.4 Collapse files when

- each file is only a few forwarding methods;
- the split forces constant jumping without isolating a responsibility;
- names differ but ownership and reason for change are identical;
- an earlier experiment left ceremonial scaffolding after the concept stabilized.

### 16.5 Collapse a submodule when

- it owns no independent interface;
- it exists only to hide private methods;
- the parent reexports everything it contains;
- every call requires importing both parent and child;
- it adds namespace ceremony without isolating dependencies or semantics.

---

## 17. Forbidden repository shapes

### 17.1 Layer-first root tree

```text
src/
├── types/
├── services/
├── managers/
├── handlers/
├── validators/
└── utils/
```

This scatters one domain change across unrelated folders and hides ownership behind generic mechanisms.

### 17.2 One module per file

A Julia module is not a class wrapper. Creating a namespace for every type or algorithm destroys the usefulness of namespaces and produces import sludge.

### 17.3 One directory per type

A type earns a directory only after it owns several coherent responsibilities.

### 17.4 Empty standard scaffold

Do not generate `types.jl`, `interfaces.jl`, `base.jl`, `plot.jl`, and `dataframe.jl` for every module before code exists. Empty symmetry is still bloat, merely well aligned.

### 17.5 `base.jl` as landfill

Only Base/Core protocol methods belong there.

### 17.6 Optional packages imported in core

Use package extensions instead of forcing every user to load plotting, tabular, meshing, or GUI dependencies.

### 17.7 Split choreography

The fixed sequence of `compute`, `validate`, `plot`, or another first-class action stays visible in one action file. Hooks may be distributed; the orchestration graph may not.

### 17.8 Dynamic include or registration machinery

Do not discover source files at runtime, mutate modules, or use registries merely to avoid explicit includes and dispatch.

### 17.9 Transitional files with permanent names

Files named `new.jl`, `old.jl`, `v2.jl`, `temporary.jl`, or `wip.jl` do not belong in a converged runtime tree. Git already performs historical storage without needing help from embalmed source files.

---

## 18. Reference scaffolds

### 18.1 Small owner in the package module

```text
src/
├── PackageName.jl
├── interfaces.jl
├── types.jl
├── material.jl
└── units.jl
```

Use while the package remains small and each file has obvious ownership.

### 18.2 Feature directories without submodules

```text
src/
├── PackageName.jl
├── grammar/
│   ├── interfaces.jl
│   └── definitions.jl
├── engine/
│   ├── types.jl
│   ├── compute.jl
│   ├── lineparameters.jl
│   └── observables.jl
└── validation/
    ├── rules.jl
    ├── errors.jl
    └── validate.jl
```

All files may still be included into `PackageName` when separate namespaces add no value.

### 18.3 Owned modules

```text
src/
├── PackageName.jl
├── grammar/
│   ├── Grammar.jl
│   ├── interfaces.jl
│   └── definitions.jl
├── engine/
│   ├── Engine.jl
│   ├── types.jl
│   ├── compute.jl
│   ├── lineparameters/
│   │   ├── lineparameters.jl
│   │   ├── constructors.jl
│   │   └── observables.jl
│   └── reduction/
│       ├── reduction.jl
│       ├── kron.jl
│       └── grouping.jl
└── plotbuilder/
    ├── PlotBuilder.jl
    ├── interfaces.jl
    ├── definitions.jl
    └── plot.jl
```

### 18.4 Nested owned submodule

```text
src/
└── cablebuilder/
    ├── CableBuilder.jl
    ├── interfaces.jl
    ├── types.jl
    └── cabledesign/
        ├── CableDesign.jl
        ├── types.jl
        ├── constructors.jl
        ├── stack.jl
        └── parts/
            ├── parts.jl
            ├── solid.jl
            └── tubular.jl
```

Use only when `CableDesign` needs an actual namespace. Otherwise keep the same directory without `CableDesign.jl` and include its files into `CableBuilder`.

### 18.5 Optional integrations

```text
ext/
├── PackageNameDataFramesExt.jl
└── PackageNameMakieExt/
    ├── PackageNameMakieExt.jl
    ├── render.jl
    ├── controls.jl
    └── export.jl
```

---

## 19. Repository-scaffolding review checklist

### Ownership

- [ ] Every source file has one obvious owner.
- [ ] Every directory can be described in one sentence.
- [ ] Shared root concepts pass the two-owner test.
- [ ] No feature is split across global mechanism folders.

### Modules

- [ ] Every submodule owns a real namespace or dependency distinction.
- [ ] No folder became a module merely because it contains several files.
- [ ] Parent and sibling imports follow a directed graph.
- [ ] Module entry files expose imports, public names, and include order.

### Files

- [ ] Filenames name a concept, action, algorithm, or protocol.
- [ ] `types.jl`, `interfaces.jl`, and `base.jl` follow their defined roles.
- [ ] Complex algorithms have precise names instead of living in helpers.
- [ ] File splitting improves navigation rather than producing forwarding confetti.

### Dispatch and orchestration

- [ ] Each first-class action has one visible action file.
- [ ] Hook declarations live with the action owner.
- [ ] Concrete declarative methods live near the definitions they explain.
- [ ] No registry or mode table duplicates native dispatch.

### Integrations

- [ ] Optional dependencies use Julia package extensions.
- [ ] Core source contains backend-neutral semantics only.
- [ ] No type piracy is introduced between unrelated third-party packages.

### Tests and docs

- [ ] `test/runtests.jl` remains the test entry point.
- [ ] Tests are grouped by contract and owner, not copied mechanically from source files.
- [ ] Module documentation states ownership, actions, results, and extension points.
- [ ] The source tree and maintained documentation describe the same structure.

### Debloating

- [ ] No `helpers`, `utils`, `misc`, or vague `common` buckets exist.
- [ ] No empty scaffold files exist.
- [ ] No obsolete `old`, `new`, `v2`, or temporary source paths remain.
- [ ] No submodule survives solely because removing it feels impolite.

---

## 20. Final rule set

The repository follows this playbook when normal development behaves predictably:

1. Find the concept owner.
2. Enter that owner’s directory.
3. Find the file named after the action, protocol, or object.
4. Add or specialize the method there.
5. Promote a file to a directory only when the concept owns several responsibilities.
6. Promote a directory to a submodule only when it needs an independent namespace or dependency contract.
7. Move optional-package code to `ext/`.
8. Keep one Template Method choreography visible in one action file.
9. Keep declarative methods close to the definitions they explain.
10. Delete structural ceremony that no longer owns anything.

The compact repository law is:

> **Owner first. Responsibility second. Directory before submodule. Explicit entry files. Local definitions. One visible choreography. Optional integrations in extensions. No junk drawers.**

---

## References to consult

### Julia language and package structure

1. **Julia Manual: Modules**  
   Explains modules, submodules, relative imports, `include`, and the fact that files are largely independent of module structure.  
   https://docs.julialang.org/en/v1/manual/modules/

2. **Pkg.jl: Creating Packages**  
   Defines the minimal package scaffold, public API declarations, testing entry point, workspaces, weak dependencies, and package extensions.  
   https://pkgdocs.julialang.org/v1/creating-packages/

3. **Julia Style Guide**  
   Supports exported methods as interfaces to owned types and standard Base naming and mutation conventions.  
   https://docs.julialang.org/en/v1/manual/style-guide/

4. **SciML Style Guide for Julia**  
   Provides a maintained large-project Julia style reference, including module-file conventions.  
   https://docs.sciml.ai/SciMLStyle/

5. **DataFrames.jl source tree**  
   Useful empirical example of feature-oriented directories included into one package module rather than one submodule per directory.  
   https://github.com/JuliaData/DataFrames.jl/tree/main/src

### Decomposition and colocation theory

6. **D. L. Parnas, “On the Criteria To Be Used in Decomposing Systems into Modules,” 1972**  
   Foundational argument for decomposing around hidden design decisions and information ownership rather than processing steps.  
   https://doi.org/10.1145/361598.361623

7. **Robert C. Martin, _Clean Architecture_, Component Cohesion chapters**  
   Source for the Common Closure Principle and Common Reuse Principle. Use the principles; spare the repository the surrounding enterprise cosplay.

8. **Angular Style Guide: Project structure**  
   Cross-language current example of organizing by feature areas, grouping closely related files, avoiding generic type-based directories, and splitting when navigation suffers.  
   https://angular.dev/style-guide

9. **Locality of Behaviour**  
   Concise statement of the readability principle behind colocation.  
   https://htmx.org/essays/locality-of-behaviour/

### Companion project playbook

10. **Dispatch-Driven Template Method Playbook for Julia**  
    Defines how extensible actions, hook methods, declarative definitions, and owned results fit inside the repository structure described here.
