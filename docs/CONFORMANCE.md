# APL Conformance Testing

APL treats verification failures as part of the language contract, not merely implementation accidents.

## Positive conformance

Valid programs are exercised through:

- unit-level verifier/interpreter tests in `tests/test_core.py`;
- executable examples in `examples/`;
- CI execution on every supported reference Python version.

Positive tests verify both accepted IR and defined execution semantics.

## Negative conformance corpus

`tests/negative/` contains complete APL programs that **must be rejected** by a conforming verifier.

The corpus is data-driven:

- each `.apl` file is an intentionally invalid program;
- `manifest.json` names every corpus file and the diagnostic fragment expected from the reference verifier;
- `tests/test_negative_corpus.py` checks that every file is listed exactly once and every listed file exists;
- each case must raise `VerificationError` for the expected reason.

The diagnostic fragment is a reference-implementation regression check. The semantic conformance requirement is the rejection itself and the corresponding violated language rule.

## Current negative coverage

The initial corpus covers:

- parameterized entry functions;
- SSA use-before-definition;
- duplicate SSA identities;
- function-call type mismatch;
- recursive call cycles;
- excessive bounded-repeat maxima;
- fixed-array arity mismatch;
- missing record fields;
- record version gating;
- reserved trap-code namespaces;
- instructions after abrupt terminators;
- unknown structured type descriptors;
- missing Draft 0.0.8 capability/effect declarations;
- effect inference/declaration mismatches;
- module capability-union mismatches;
- unknown and duplicate effect declarations;
- Draft 0.0.9 host-effect version gating;
- deterministic host operation argument typing;
- missing, malformed, or excessive Draft 0.0.10 resource-limit declarations;
- missing Draft 0.0.11 contract lists;
- invalid contract result scope, predicate typing, and duplicate contract identifiers;
- pre-0.0.12 range-type use;
- invalid range bounds and invalid explicit range conversion operands;
- pre-0.0.13 quantity-type use;
- invalid unit symbols/exponents and incompatible quantity arithmetic;
- pre-0.0.14 invariant declarations;
- malformed/duplicate/non-Boolean invariant definitions;
- invalid invariant-check argument typing and disallowed invariant-to-invariant definitions.

The corpus should grow whenever a verifier bug, ambiguity, or new language rule is introduced.
