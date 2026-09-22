# APL WebAssembly backend

Status: **M4 scalar backend checkpoint**

The backend compiles verified APL through normalized LIR 0.1 into a real WebAssembly 1.0 binary.

## Current compilation path

```text
APL semantic IR
    |
    v
semantic verifier
    |
    v
normalized LIR 0.1
    |
    v
LIR verifier
    |
    v
WASM scalar backend
    |
    v
WebAssembly 1.0 binary
```

The backend never compiles unverified source directly.

## Export ABI

The module exports exactly one public entry function:

```text
apl_entry
```

It corresponds to the APL module entry function. Because APL entry functions have zero parameters, `apl_entry` has no WebAssembly parameters.

APL types map as follows in the scalar checkpoint:

| APL | WebAssembly |
|---|---|
| `i64` | `i64` |
| `bool` | `i32` with canonical values 0/1 |
| `unit` | no result |

## Trap import ABI

Compiled modules import:

```text
apl.trap(i32) -> ()
```

The host must throw/abort when called.

Current deterministic trap codes are:

| Code | Meaning |
|---:|---|
| 1 | `apl.i64_overflow` |
| 2 | `apl.division_by_zero` |

The compiler emits an `unreachable` immediately after the import call so a nonconforming host that returns still cannot continue execution.

## Supported LIR subset

The scalar checkpoint supports:

- scalar `i64` and `bool` constants;
- checked `i64.add`, `i64.sub`, and `i64.mul`;
- checked `i64.div` and `i64.rem`;
- signed `i64` ordered comparisons;
- scalar equality;
- Boolean not/and/or;
- pure function calls;
- verified multi-block CFG with `br`/`cond_br` and typed block-parameter transfers;
- scalar/unit returns;
- legacy `budget.step` nodes when source APL has no runtime resource budget.

Compilation currently rejects:

- strings;
- arrays, records, ranges and quantities;
- bounded `repeat` until its runtime guard is mapped to the trap ABI;
- contracts/invariant guards;
- explicit traps;
- host effects/capabilities;
- source APL resource budgets.

Unsupported semantics fail at compile time with `CompilationError`; they are never silently approximated.

## Checked integer semantics

WebAssembly wraps `i64.add/sub/mul`, while APL requires overflow traps. The backend emits explicit overflow checks: add/sub use signed overflow predicates after the wrapped operation, while multiplication verifies signed bounds before executing the multiply. Overflow invokes `apl.trap(1)`.

Division emits explicit checks for:

- divisor zero -> trap 2;
- `INT64_MIN / -1` -> trap 1.

Remainder emits an explicit divisor-zero check. WebAssembly's signed remainder already yields zero for the `INT64_MIN rem -1` edge case required by APL.

## CLI

```text
apl compile-wasm source.apl output.wasm
```

The command verifies source APL, lowers it to verified LIR, compiles the supported subset, and writes a binary WebAssembly module.

## Differential testing

CI loads emitted binaries with the native Node/WebAssembly runtime and compares successful entry results against the APL reference interpreter. It also checks the deterministic trap ABI for overflow and division-by-zero.

This is the first WASM backend checkpoint, not the completion of M4. Subsequent work expands CFG lowering, resource budgets, structured data, effects, and full trap diagnostics.
