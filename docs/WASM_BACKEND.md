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
| 3 | `apl.repeat_negative_count` |
| 4 | `apl.repeat_count_exceeds_max` |
| 5 | `apl.resource_limit` for exhausted `steps` |
| 6 | `apl.precondition_failed` |
| 7 | `apl.postcondition_failed` |
| 8 | `apl.invariant_failed` |
| 9 | `apl.range_violation` |

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
- bounded `repeat` loops and their runtime count guards;
- module-wide `steps` resource budgets shared across function calls;
- contract and reusable-invariant guards;
- bounded range refinement/widening represented as checked `i64`;
- symbolic quantities represented as checked `i64` values with static type algebra already verified by LIR;
- scalar/unit returns.

Compilation currently rejects:

- strings;
- arrays and records;
- explicit application-defined traps, pending a diagnostic-preserving trap ABI;
- host effects/capabilities (`console.write`, filesystem and network reads);
- output-line and host-read budget consumption until those corresponding effects are implemented.

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

CI loads emitted binaries with the native Node/WebAssembly runtime and checks successful compiled results for scalar arithmetic, calls, structured `if`, bounded `repeat`, step budgets, contracts, ranges, quantities and invariants. It also validates deterministic trap codes for arithmetic, repeat guards, exhausted step budgets, failed contracts/invariants and range violations.

This is a substantial WASM backend checkpoint, not the completion of M4. Remaining backend work centers on structured data/string representation, observable host effects, output/host-read budgets, application-defined trap diagnostics, and broader optimization/equivalence testing.
