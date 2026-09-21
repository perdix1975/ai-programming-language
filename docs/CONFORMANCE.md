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
- unknown structured type descriptors.

The corpus should grow whenever a verifier bug, ambiguity, or new language rule is introduced.
