# APL Roadmap

## M0 — Executable semantic seed

- [x] public repository
- [x] versioned JSON IR
- [x] primitive type verifier
- [x] SSA-style value discipline
- [x] deterministic canonical encoding/hash
- [x] reference interpreter
- [x] CLI: verify/run/canonicalize/hash
- [x] initial conformance tests
- [x] CI green on supported Python versions

## M1 — Real programming core

- [x] typed function calls and forward references
- [x] structured value-producing `if`
- [x] acyclic call-graph verification
- [x] bounded structured `repeat` with explicit static maximum
- [x] division/remainder and ordered comparisons with defined edge semantics
- [x] immutable fixed-length arrays with structured type descriptors
- [x] immutable structural records with named fields
- [x] explicit deterministic trap model with stable machine-readable codes
- [x] file-based negative conformance corpus with manifest completeness checks

## M2 — Effects and safety

- [x] formal exact function effect annotations
- [x] exact module capability declarations plus explicit runtime grants
- [x] deterministic fixture-backed filesystem/network capability prototypes
- [x] deterministic fixture-backed host interface
- [x] deterministic steps/output/host-read resource limits with host tightening

## M3 — Contracts and richer types

- [x] typed declarative preconditions/postconditions with deterministic runtime enforcement
- [ ] refinement/range types
- [ ] units/dimensions exploration
- [ ] machine-checkable invariants

## M4 — Compiler path

- normalized lower IR
- WASM backend
- optimization equivalence tests
- differential testing: interpreter vs compiled output

## M5 — AI-native layer

- semantic macro/primitive mechanism
- machine-generated primitive identifiers
- explicit lowering proofs/checks
- learned cost model
- profile-guided specialization
- human audit projection

## M6 — Production experiments

Use APL to implement progressively larger real applications and measure:

- correctness defects;
- IR/token compactness;
- generation reliability;
- verifier rejection rate;
- compilation/execution performance;
- optimization opportunities unavailable to conventional source-level generation.
