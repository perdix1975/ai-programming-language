# M4 compiler equivalence

Status: **M4 conformance contract**

This document defines how APL checks that lowering, optimization, and WebAssembly compilation preserve observable language semantics.

## 1. Three execution paths

Every differential case is evaluated through:

1. the reference semantic interpreter;
2. WebAssembly compiled from verified normalized LIR;
3. WebAssembly compiled from the deterministically optimized version of the same LIR.

The interpreter is the semantic oracle for M4.

## 2. Compared observable outcome

For a successful program the differential outcome contains:

- return type;
- recursively normalized return value;
- ordered output lines.

For a trapping program the outcome contains:

- stable machine-readable trap code;
- output lines completed before the trap.

Built-in diagnostic prose is intentionally not used as the equivalence key because the language specification defines the stable trap code as the semantic interface. Application-trap diagnostic payloads remain covered independently by the exact WebAssembly trap-ABI tests.

## 3. Value normalization

Differential values use a JSON-safe canonical projection:

- `i64`, range values, and quantity values -> decimal strings;
- `bool` -> JSON Boolean;
- `string` -> decoded Unicode string;
- arrays -> ordered arrays of recursively normalized values;
- records -> objects with lexicographically ordered field names;
- `unit` -> `null`.

This avoids host-language integer precision differences while preserving exact APL value meaning.

## 4. Differential manifest

`tests/differential_manifest.json` is the single data-driven corpus.

Each case identifies:

- a complete APL example;
- optional runtime capability grants;
- an optional deterministic host fixture.

The corpus intentionally includes both success and failure paths across:

- arithmetic and overflow;
- calls and structured control;
- bounded repeat;
- strings;
- arrays and records;
- recursive structural equality;
- capabilities and host effects;
- all resource budgets;
- contracts and reusable invariants;
- range and quantity semantics;
- explicit application traps and built-in runtime traps.

## 5. Optimizer safety rules

The current optimizer is deliberately conservative.

It may perform:

- safe constant folding for primitive arithmetic/comparisons/Boolean expressions;
- constant selection of verified CFG branches;
- compile-time fixed array-length replacement.

It must not:

- remove or reorder `budget.step`;
- fold an operation whose original execution would trap;
- change function effects or module capabilities;
- remove effectful operations;
- alter stable trap ordering.

Examples:

- `40 + 2` may become constant `42`;
- `INT64_MAX + 1` must remain checked addition;
- `7 / 0` must remain checked division;
- a constant `cond_br` may become `br`, but the unselected block remains in the verified LIR so static effect metadata is unchanged.

## 6. Determinism and idempotence

For the same verified LIR, optimization must produce byte-for-byte identical canonical JSON on repeated runs.

Applying the optimizer to its own output must produce exactly the same LIR.

CI verifies both properties.

## 7. Required M4 gate

M4 compiler equivalence is considered passing only when:

- every manifest case matches the interpreter in baseline WebAssembly;
- every manifest case matches the interpreter in optimized WebAssembly;
- baseline and optimized WebAssembly outcomes match each other;
- the corpus exercises at least one real optimizer transformation;
- optimized LIR independently passes `verify_lir`;
- optimizer output is deterministic and idempotent.

The gate is executed by:

```text
python tests/run_differential.py
```
