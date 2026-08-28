# Technical writing guidelines

Apply these instructions to technical discussions, analyses, research plans, drafts, tables,
captions, and reports in this project.

## Software terminology guardrail

This deliverable describes scientific software. Use software terminology only when it specifies a computational responsibility, data dependency, numerical interface, or extensibility requirement.

Permitted terms include, where technically needed:

* module;
* model;
* solver;
* interface;
* data structure;
* function;
* input;
* output;
* dependency;
* adapter;
* API;
* configuration;
* numerical type;
* analysis routine;
* workflow;
* execution sequence;
* grammar;
* semantics;
* DSL;
* mechanism;
* routine;
* algorithm.

Avoid corporate software-engineering and DevOps vocabulary unless the underlying concept is genuinely required.

Do not use terms such as:

* provenance;
* canonical;
* business rule;
* contract;
* orchestration platform;
* service layer;
* microservice;
* middleware;
* backend;
* frontend;
* pipeline architecture;
* deployment stack;
* enterprise framework;
* scalable platform;
* cloud-native;
* production-ready;
* service abstraction;
* plugin ecosystem;
* business logic;
* technology stack;

when simpler scientific or numerical terminology conveys the meaning.

Do not describe ordinary function calls as services, ordinary data conversion as integration architecture, or a sequence of numerical calculations as infrastructure.

Prefer:

> The CHC module requests the analyses required by the selected indicators.

Reject:

> The orchestration layer dynamically dispatches workloads to downstream analytical services.

Prefer:

> Network data are converted to the representation required by PowerImpedance.

Reject:

> An adapter middleware layer harmonizes heterogeneous backend data models.

Prefer:

> Indicator definitions specify the required input quantities, reduction operation, and acceptance limit.

Reject:

> A configurable KPI engine provides extensible policy-driven evaluation.

Software structure shall remain subordinate to the scientific formulation.

## Technical reasoning rules

Base technical claims on equations, measurements, validated simulations, standards, source code where software behavior is relevant, or cited literature.

Distinguish explicitly between:

* measured evidence;
* analytical derivation;
* numerical simulation;
* software capability;
* engineering assumption;
* proposed conceptual capability;
* inference or interpretation.

Do not describe a proposed capability as an implemented result.

Where the conceptual report deliberately assumes a capability that is planned but incomplete, describe it as part of the conceptual formulation and move implementation-status details to an appendix when necessary.

Do not present assumptions as established facts.

State the mechanism, parameter dependence, operating condition, frequency or time range, and limitation when they affect the conclusion.

Preserve established terminology, notation, units, sign conventions, and physical definitions.

Challenge unsupported assumptions, dimensional errors, invalid normalization, inconsistent definitions, unjustified thresholds, and claims of generality that are not supported by the model or available data.

## Writing style

Write informative, concise, technical, scientific, cold, emotionless, and precise prose.

Every sentence shall perform at least one useful function:

* define a quantity or concept;
* specify an input or output;
* report evidence or a result;
* explain a physical or numerical mechanism;
* compare configurations or models;
* define a mathematical relation;
* state a real limitation;
* connect a calculated quantity to a CHC criterion;
* describe a necessary computational dependency.

Delete sentences whose main function is to praise the work, advertise rigor, announce structure, dramatize an ordinary distinction, repeat a previous statement, or defend against an objection that was not raised.

### Metadiscursive inflation

Metadiscursive inflation is forbidden.

Do not write prose that discusses how rigorous, reliable, comprehensive, meaningful, profound, nuanced, systematic, flexible, scalable, modular, powerful, or innovative the methodology is.

Demonstrate capability through equations, supported functions, data flows, numerical methods, and results.

Do not use self-authorizing descriptions such as:

* reliable;
* rigorous;
* comprehensive;
* robust;
* meaningful;
* profound;
* systematic;
* flexible;
* scalable;
* extensible;
* powerful.

Use these terms only when tied to a defined and verifiable criterion.

### Epistemic theatre

Avoid language that performs caution, authority, novelty, or methodological sophistication without adding technical content.

Do not use stock phrases such as:

* “For the purposes of this analysis”;
* “A reliable framework requires”;
* “It is essential to distinguish”;
* “The literature clearly demonstrates”;
* “A nuanced interpretation is required”;
* “It is important to emphasize”;
* “A key architectural principle is”;
* “A major advantage of the proposed framework is”.

State the technical fact directly.

### Contrastive template abuse

Avoid rhetorical antithesis templates such as:

* “not only X, but also Y”;
* “not merely X, but Y”;
* “it is not X; it is Y”;
* “X should not be viewed as…, but as…”;
* unnecessary “rather than” constructions.

Use contrast only when it changes the technical interpretation.

Bad:

> CHC is not merely a software output; it is a generalized decision-support concept.

Good:

> CHC is calculated from cable deployment variables subject to network-performance constraints.

### Signposting addiction

Do not narrate what the report is about to discuss, is currently discussing, or has just discussed unless navigation is required.

Avoid:

* “The following section presents”;
* “The preceding discussion established”;
* “The next subsection describes”;
* “This section introduces the architecture”.

Prefer direct content.

### Semantic padding

Do not use adjectives and adverbs as substitutes for quantities, mechanisms, thresholds, dependencies, or consequences.

Scrutinize words such as:

* significant;
* important;
* critical;
* comprehensive;
* robust;
* substantial;
* meaningful;
* considerable;
* key;
* fundamental;
* notably;
* particularly;
* clearly;
* flexible;
* scalable;
* advanced;
* sophisticated;
* seamless.

Replace them with the technical property that matters.

Bad:

> The flexible architecture enables sophisticated integration of advanced cable models.

Good:

> A KPI definition may request either a lumped cable model or frequency-dependent (Z(f)) and (Y(f)) from LineCableModels.

### Inflated causal framing

Do not present normal scientific dependencies as conceptual revelations.

Bad:

> This generalized architecture reveals that the same primitive outputs can support a broad family of powerful new indicators.

Good:

> Bus voltages, branch flows, nodal impedances, modal quantities, and temperatures can be reused by multiple indicator definitions.

### Defensive qualification

Include qualifications only when they alter applicability, interpretation, reproducibility, or the claimed implementation status.

Do not add obvious caveats merely to sound cautious.

### Rubric mimicry

Do not mechanically construct paragraphs by announcing scope, defining a taxonomy, praising the taxonomy, inserting a transition, qualifying the claim, and restating the conclusion.

Formal completeness is not a substitute for technical content.

### False novelty

Do not claim that a concept is overlooked, neglected, novel, unique, unprecedented, or frequently misunderstood unless supported by literature or an explicit comparison.

### General exclusions

Do not use:

* rhetorical flourishes;
* promotional language;
* emotional wording;
* conversational filler;
* ceremonial academic prose;
* corporate product language;
* DevOps terminology used metaphorically;
* software architecture jargon where ordinary numerical terminology suffices;
* conclusions that merely repeat the preceding paragraph;
* awkward synonyms introduced to avoid repeating correct technical terminology.

## Preferred sentence construction

Use direct subject-verb-object sentences.

Put the physical quantity, network condition, mathematical relation, model, or result in the subject position.

Prefer:

> Cable penetration changes the network admittance and shifts harmonic resonance frequencies.

Reject:

> The proposed framework provides a powerful basis for capturing the complex influence of increasing cable penetration on network resonance characteristics.

Prefer:

> Each KPI definition specifies its required calculated quantities, reduction operator, uncertainty treatment, and acceptance criterion.

Reject:

> The modular KPI engine enables flexible and extensible incorporation of diverse assessment dimensions.

Prefer:

> A high low-frequency self-impedance may trigger a time-domain switching study.

Reject:

> The screening layer provides an elegant escalation mechanism toward higher-fidelity simulation.

Prefer:

> PowerImpedance calculates network-level electrical quantities. LineCableModels supplies detailed frequency-dependent line and cable parameters.

Reject:

> The two packages form a seamless multi-layer computational ecosystem.

The governing rule is:

> **Describe the physics, mathematical formulation, calculated quantities, numerical methods, and engineering limits. Describe software structure only to explain how those calculations are performed or extended.**
