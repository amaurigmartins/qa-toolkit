# STECode rule provenance and coverage

The `STECode` style derives from every text file under the ignored
`templates/STE-Code-Current/**/*.txt` tree. The consolidated source is
`ste-code/artifacts/llms-full.txt`. The `level-*`, `level0`, and `level1` through `level5`
artifacts restate or expand the same rules. The root `requirements.txt` contains generation
dependencies and no writing rules.

The ignored corpus is a design input only. Runtime checks use the immutable files packaged here.
Vale does not call a model, download a style, or read the corpus in a target repository.

## Managed checks

Errors are mechanically specific and block the gate. Warnings identify deterministic text
patterns whose grammatical role or scientific context still needs review.

| Vale check | Level | Mechanical responsibility |
|---|---|---|
| `SoftwareTerminology` | error | Corporate and service-oriented terminology prohibited by the scientific-software guardrail |
| `PreferredTerms` | error | Corpus-listed inflated verbs and their inflections |
| `UnapprovedComparatives` | error | Explicit incorrect adjective forms and color comparatives from Rule 1.4 |
| `AmericanSpelling` | error | Explicit British-to-American spelling pairs from Rule 1.14 |
| `BritishSpelling` | error | Explicit American-to-British spelling pairs when the repository selects `en-GB` |
| `Contractions` | error | Apostrophe contractions from Rule 4.2 |
| `Semicolons` | error | Prose semicolons from Rule 8.1 |
| `SentenceLength` | error | Descriptive sentences over 25 STE-Code words |
| `InflatedProse` | error | Unambiguous verbose, promotional, and metadiscursive phrases |
| `WeakHedges` | error | Selected weak hedges that omit a condition or measured uncertainty |
| `ForbiddenConnectors` | error | The four connectors explicitly rejected by Rule 4.4 |
| `PhrasalVerbs` | error | The explicit prohibited phrasal-verb catalog in Rule 9.3 |
| `InformalTerms` | error | Explicit vague and informal terms from Rule 1.10 and the anti-pattern catalog |
| `NominalizedActions` | error | High-confidence indirect action phrases that contain an `of` complement |
| `SequentialInstructions` | error | `and then` and explicit three-step prose sequences |
| `NoteCommands` | error | A `NOTE:` label immediately followed by a known imperative |
| `SafetyLabels` | error | Risk labels other than `WARNING`, `CAUTION`, and `NOTE` |
| `SafetySignalFormat` | error | Safety signal case, colon spacing, and initial capitalization |
| `NestedParentheses` | error | Nested parentheses prohibited by Rule 8.3 |
| `PassiveVoice` | warning | Auxiliary-plus-participle patterns, including irregular participles |
| `ComplexVerbForms` | warning | Perfect, progressive, modal-passive, and related auxiliary constructions |
| `AmbiguousPronouns` | warning | Bare demonstratives that do not name a referent |
| `ParagraphLength` | warning | Paragraphs over six sentences |
| `ProcedureSentenceLength` | warning | List items over the 20-word procedural limit |
| `ProcedureMood` | warning | List items that use a reader plus modal instead of a direct imperative |
| `ProcedureFutureTense` | warning | Future tense in list items that can represent procedures |
| `ConditionOrder` | warning | Known imperative verbs followed by a trailing condition |
| `KnownHyphenation` | warning | Explicit code-domain compounds from Rules 2.3, 8.2, and 8.7 |
| `UnexpandedAcronyms` | warning | First unresolved use of an uppercase initialism in each document |
| `ListCapitalization` | warning | Vertical list items that start with a lowercase prose word |
| `UnsupportedQualifiers` | warning | Promotional or evidentiary qualifiers that need a stated criterion |

## Rule-to-corpus matrix

Every numbered STE-Code requirement has a disposition below. “Review” means the requirement
depends on meaning, part of speech, document purpose, or domain terminology and cannot be proved by
a repository-independent Vale rule.

| Rule | Automated coverage | Remaining responsibility |
|---|---|---|
| 1.1 | `PreferredTerms`, `InflatedProse`, `PhrasalVerbs`, `SoftwareTerminology` | Review the full approved-word gate and technical-term exemptions. |
| 1.2 | None | Review approved parts of speech; POS tagging is not reliable for project and scientific terms. |
| 1.3 | None | Review whether an approved word has its controlled meaning. |
| 1.4 | `PreferredTerms`, `UnapprovedComparatives`; `ComplexVerbForms` warning | Review arbitrary inflections and adjective forms against the dictionary. |
| 1.5 | `SoftwareTerminology` applies the repository override | Review whether a noun belongs to a scientific or code-domain category. |
| 1.6 | None | Review the technical-noun exemption for unapproved words. |
| 1.7 | None | Review whether a project noun is being used as a verb. |
| 1.8 | CSpell and repository vocabulary, outside Vale | Maintain approved project and scientific terminology. |
| 1.9 | `InflatedProse`, `SoftwareTerminology` | Review whether a selected technical noun is the shortest precise term. |
| 1.10 | `PhrasalVerbs`, `InformalTerms`, `InflatedProse`, `SoftwareTerminology` | Review domain jargon that has no universal literal signature. |
| 1.11 | None | Review whether two terms name the same scientific or computational item. |
| 1.12 | Identifier and repository vocabulary checks, outside Vale | Review whether a prose verb is an approved technical operation. |
| 1.13 | `NominalizedActions`; `ComplexVerbForms` warning | Review other technical verbs used as nouns. |
| 1.14 | `AmericanSpelling` or `BritishSpelling`, selected by repository locale | Preserve quoted text and official technical names through markup or exact finding overrides. |
| 2.1 | None | Review the three-word technical-noun limit after identifying the noun phrase. |
| 2.2 | `UnexpandedAcronyms` warning | Review terms outside the supported initialism and same-line expansion forms. |
| 2.3 | `KnownHyphenation` warning | Review arbitrary compound modifiers and official term spelling. |
| 3.1 | `PreferredTerms`; `ComplexVerbForms` warning | Review the complete verb dictionary and technical-verb exemptions. |
| 3.2 | `ComplexVerbForms` warning | Review tense when a surface form is grammatically ambiguous. |
| 3.3 | `PassiveVoice` and `ComplexVerbForms` warnings | Review whether a participle describes a condition or an action. |
| 3.4 | `ComplexVerbForms` and `PassiveVoice` warnings | Rewrite each reported auxiliary construction in context. |
| 3.5 | `ComplexVerbForms` warning | Review whether an `-ing` word is a verb, noun, adjective, or technical modifier. |
| 3.6 | `PassiveVoice` warning | Active voice is required unless the actor is genuinely unknown. |
| 3.7 | `NominalizedActions`, `PreferredTerms` | Review nominalizations that are also defined scientific operations. |
| 4.1 | `InflatedProse`, `UnsupportedQualifiers`, `SentenceLength`, `SequentialInstructions` | Review sentence topics and abstract claims. |
| 4.2 | `Contractions` | Review omitted articles or arguments that require grammar and domain knowledge. |
| 4.3 | `SequentialInstructions`; `ListCapitalization` warning | Review when complex prose needs a vertical list and whether items use parallel grammar. |
| 4.4 | `ForbiddenConnectors` | Review whether the remaining connector expresses the actual relation. |
| 4.5 | `AmbiguousPronouns` warning | Review missing articles and demonstrative adjectives. |
| 5.1 | `ProcedureSentenceLength` and `ProcedureFutureTense` warnings | Confirm that a list item is procedural before applying procedure-only rules. |
| 5.2 | `SequentialInstructions` | Review multiple simultaneous actions joined by `and`. |
| 5.3 | `ProcedureMood` and `ProcedureFutureTense` warnings | Confirm whether a list item is an instruction or a description. |
| 5.4 | `ConditionOrder` warning | Review command/result clauses where the surface order is permitted. |
| 5.5 | `NoteCommands` | Review commands whose imperative verb is domain-specific. |
| 6.1 | `ParagraphLength` warning | Review whether information proceeds from general to specific. |
| 6.2 | `ForbiddenConnectors` | Review the logical relation and reuse of key terms. |
| 6.3 | `SentenceLength` | None for the mechanical 25-word limit. |
| 6.4 | `ParagraphLength` warning | Review paragraph boundaries and related information. |
| 6.5 | None | Review topic unity; topic classification is semantic. |
| 6.6 | `ParagraphLength` warning | None for the mechanical six-sentence count. |
| 7.1 | `SafetyLabels`, `SafetySignalFormat` | Review whether the selected signal word matches the actual risk. |
| 7.2 | `ConditionOrder` warning | Review whether a safety instruction starts with the command or its condition. |
| 7.3 | None | Review whether the safety text explains the real risk or result. |
| 8.1 | `Semicolons` | None for the semicolon prohibition. |
| 8.2 | `KnownHyphenation` warning | Review arbitrary compounds and predicate-versus-attributive use. |
| 8.3 | `NestedParentheses` | Review whether non-nested parentheses serve one of the permitted purposes. |
| 8.4 | Markdown parsing protects list structure; `ListCapitalization` warning | Review whether introductory text and list punctuation form complete sentences. |
| 8.5 | `SentenceLength` counts a parenthesized span as one word | Review unmatched or semantic misuse of parentheses. |
| 8.6 | `SentenceLength` counts known quantities, identifiers, numbers, and quoted spans as units | Proper names and unknown measurement units remain a review concern. |
| 8.7 | `SentenceLength` counts hyphenated compounds as one word; `KnownHyphenation` warns | Review whether the hyphenated words form one unit. |
| 9.1 | `PreferredTerms`, `InflatedProse`, `NominalizedActions` | Review rewrites when literal substitution changes the scientific meaning. |
| 9.2 | Literal substitution checks | Review approved meaning and part of speech. |
| 9.3 | `PhrasalVerbs` | Review verb-plus-preposition combinations not in the explicit catalog. |
| 9.4 | Literal checks enforce their specified forms | Review concept-level consistency across files and project terminology. |

## Tool ownership

Vale owns wording in tracked Markdown, source-mapped LaTeX prose views, and extracted Python
and Julia docstrings. CSpell owns spelling coverage beyond the explicit Rule 1.14 variants and
retains the repository vocabulary. Pydoclint owns Python docstring structure and signature
agreement. Existing AST and identifier checks remain authoritative for function, type, and variable
names. Grain retains structural slop checks, except for its overlapping hedge-word check.

The style intentionally contains no Vale spelling rule, full vocabulary allowlist, general grammar
parser, or scientific-claim checker. Those additions would either overlap an existing owner or
misclassify valid scientific terminology. Software structure remains subordinate to the scientific
formulation.
