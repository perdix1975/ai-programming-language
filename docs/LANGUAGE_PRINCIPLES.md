# APL Language Principles

APL is designed **AI-first, semantics-first, and verification-first**. Human-readable syntax is a projection of the language, not its foundation.

## 1. Meaning precedes syntax

The normative program is a typed semantic representation. Surface syntaxes may exist, but they must lower into the same canonical semantic model.

## 2. No undefined behavior

For every valid program, each operation has defined behavior. Exceptional states such as integer overflow must have defined semantics (for v0, signed i64 overflow traps).

## 3. Explicit types

Values have explicit types. The verifier rejects type ambiguity and illegal combinations before execution.

## 4. Explicit effects

Pure computation and observable effects must be distinguishable in the IR. File, network, process, device, database, and similar access will require explicit capabilities.

## 5. Determinism by default

Given the same program, inputs, capabilities, and specified execution environment, deterministic operations must produce the same semantic result. Sources of nondeterminism must be declared.

## 6. Canonical identity

A valid program has a deterministic canonical representation and content identity. This supports caching, reproducibility, equivalence work, signatures, and AI-to-AI exchange.

## 7. Verifiability before optimization

The reference semantics are authoritative. Optimizers and native backends may transform a program only when they preserve those semantics.

## 8. AI-native evolution

APL may introduce machine-generated primitives and representations that are inconvenient for humans to author directly. Such extensions must still have versioned semantics and a verifiable lowering path.

## 9. Human auditability

Humans do not need to author the canonical IR, but tooling must be able to project programs into useful explanations: data dependencies, effects, capabilities, contracts, and externally observable behavior.

## 10. Versioned semantics

The language version is part of every program. Semantic changes require an explicit version transition; silently changing the meaning of existing valid programs is forbidden.

## 11. Portable semantics, target-aware realization

APL defines what a program means independently of a CPU/GPU/runtime target. Backends may specialize execution for hardware while preserving the defined result and effects.

## 12. Small trusted core

The trusted semantic core should stay as small as practical. Rich abstractions should normally lower into simpler verified primitives.
