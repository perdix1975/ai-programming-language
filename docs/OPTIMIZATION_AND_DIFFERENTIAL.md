# M4 optimization and differential verification

Status: **implemented**

This document defines the verification strategy used to close the APL M4 compiler-path milestone.

## 1. Three execution paths

Every differential case is evaluated through three independent paths:

```text
APL semantic IR
    |
    +--> reference interpreter
    |
    +--> verified LIR --> baseline WASM
    |
    +--> verified LIR --> optimizer --> verified optimized LIR --> optimized WASM
```

Both compiled outcomes must match the reference interpreter.

## 2. Manifest-driven corpus

The corpus is declared in:

```text
tests/differential_manifest.json
```

Each case names one APL source file and optional runtime context:

- granted capabilities;
- deterministic host fixture;
- host availability;
- whether exact application-trap diagnostics are compared.

The same source may appear in multiple cases with different runtime conditions, for example successful capability grants versus capability denial.

The current corpus covers:

- legacy 0.0.1 behavior and current 0.0.14 behavior;
- checked arithmetic and arithmetic traps;
- function calls and structured `if`;
- bounded `repeat`;
- strings;
- immutable arrays and records;
- recursive structured equality;
- structured return values;
- console output;
- deterministic filesystem/network reads;
- capability denial;
- host-unavailable and missing-resource failures;
- all three resource-budget classes;
- preconditions and postconditions;
- reusable invariants;
- range refinements;
- symbolic quantities;
- explicit application traps;
- array bounds traps.

## 3. Semantic outcome normalization

The Python reference runner executes each case with the reference interpreter and serializes a canonical semantic outcome.

Successful outcomes contain:

```json
{
  "status": "ok",
  "type": "...",
  "value": "...",
  "output": []
}
```

Values are normalized recursively:

- `i64`, range and quantity integers use decimal strings, avoiding JSON/JavaScript precision loss;
- Boolean values remain Booleans;
- strings remain Unicode strings;
- arrays become ordered JSON arrays;
- records become field-name objects with recursively normalized values;
- `unit` becomes `null`.

Trapping outcomes contain the machine-readable APL trap code and output emitted before the trap.

Application-defined traps additionally compare exact code, message and semantic source location because that information is preserved by the current WASM ABI.

Built-in numeric WASM traps are compared by their canonical `apl.*` code.

## 4. Compiled result decoding

The reference Node/WebAssembly runtime decodes compiled return values from the same ABI used by the backend:

- `i64`/range/quantity -> signed 64-bit value;
- `bool` -> canonical i32 Boolean;
- string -> packed UTF-8 slice;
- array -> immutable heap pointer plus static type;
- record -> immutable heap pointer plus static type.

Arrays and records are decoded recursively, so differential testing is not limited to scalar entry results.

## 5. Optimizer 0.1

`src/apl/optimize.py` implements deterministic local constant folding over verified LIR.

It currently folds only operations whose result can be determined without changing trap behavior:

- checked `i64.add/sub/mul` when the mathematical result remains in signed 64-bit range;
- `i64.div/rem` only when division is defined and non-overflowing;
- signed integer comparisons;
- primitive equality;
- Boolean `not/and/or`;
- fixed `array.len`.

The optimizer deliberately does **not** fold an operation when doing so could remove a required trap, including:

- signed arithmetic overflow;
- division by zero;
- `INT64_MIN / -1`.

## 6. Resource-accounting preservation

Normalized LIR represents each semantic source step as an explicit `budget.step`.

Optimizer 0.1 never deletes, reorders or merges `budget.step` operations.

Therefore replacing a safe pure arithmetic/comparison operation with a constant does not reduce the APL semantic step count.

The optimizer output is independently passed through `verify_lir` before compilation.

## 7. Determinism and idempotence

The optimizer is required to satisfy:

```text
optimize(L) == optimize(L)
optimize(optimize(L)) == optimize(L)
```

for the same verified LIR `L`.

Tests also require optimized WebAssembly generation to be deterministic.

## 8. Equivalence requirement

CI generates one interpreter reference result for every manifest case, then compiles the same source twice:

1. baseline verified LIR -> WASM;
2. optimized verified LIR -> WASM.

Both compiled outcomes are compared structurally against the interpreter result.

This simultaneously verifies:

- interpreter vs compiler equivalence;
- optimizer vs unoptimized compiler equivalence;
- preservation of observable output;
- preservation of machine-readable trap behavior;
- structured value representation across the compiler/runtime boundary.

## 9. CLI

The optimizer is available directly:

```text
apl optimize-lir source.apl
apl compile-wasm source.apl output.wasm --optimize
```

`optimize-lir` verifies source APL, lowers to normalized LIR, optimizes it, verifies the optimized LIR, and emits canonical JSON.

`compile-wasm --optimize` uses the same verified optimization pass before WebAssembly generation.

## 10. M4 completion criterion

M4 is considered complete when all of the following hold together:

- normalized LIR has an independent verifier;
- the current semantic surface has a real WebAssembly execution path;
- optimized LIR is independently verified;
- baseline compiled execution matches the reference interpreter across the differential corpus;
- optimized compiled execution matches the same reference outcomes.

Those conditions are now enforced continuously by CI.
