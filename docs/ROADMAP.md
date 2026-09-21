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
- [ ] CI green on supported Python versions

## M1 — Real programming core

- function calls
- structured `if`
- bounded/structured loops
- division and ordered comparisons with defined edge semantics
- arrays/records
- explicit error/trap model
- more comprehensive conformance suite

## M2 — Effects and safety

- formal effect annotations
- capability declarations
- filesystem/network capability prototypes
- deterministic host interface
- resource limits

## M3 — Contracts and richer types

- preconditions/postconditions
- refinement/range types
- units/dimensions exploration
- machine-checkable invariants

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
