# APL WebAssembly backend

Status: **M4 executable backend checkpoint**

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
WASM backend
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

APL values map to the current WebAssembly ABI as follows:

| APL | WebAssembly |
|---|---|
| `i64` | `i64` |
| `bool` | `i32` with canonical values 0/1 |
| `string` | packed `i64` UTF-8 slice handle: `(ptr << 32) | byte_length` |
| fixed array | `i32` immutable heap pointer; 8-byte element slots |
| structural record | `i32` immutable heap pointer; sorted 8-byte field slots |
| range / quantity | `i64` after static type verification |
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
| 5 | `apl.resource_limit` for exhausted `steps`, `output_lines`, or `host_reads` |
| 6 | `apl.precondition_failed` |
| 7 | `apl.postcondition_failed` |
| 8 | `apl.invariant_failed` |
| 9 | `apl.range_violation` |
| 10 | `apl.array_index_oob` |

The compiler emits an `unreachable` immediately after the import call so a nonconforming host that returns still cannot continue execution.

## Supported semantic surface

The current backend supports:

- `i64`, `bool`, UTF-8 `string`, bounded range and symbolic quantity values;
- checked `i64.add/sub/mul/div/rem`;
- signed comparisons, Boolean operators and equality;
- content equality for strings and recursive structural equality for immutable arrays/records;
- typed function calls;
- verified multi-block CFG with `br`/`cond_br` and block-parameter transfers;
- bounded `repeat` loops and their runtime count guards;
- immutable fixed-length arrays with checked indexing and exact length;
- immutable structural records with canonical sorted-field layout;
- module-wide `steps`, `output_lines`, and `host_reads` resource budgets;
- versioned capability enforcement for `console.write`, `fs.read_text`, and `net.get_text`;
- deterministic fixture-backed host reads through the runtime ABI;
- contracts, reusable invariants, range refinements and quantities;
- application-defined traps preserving exact code, message and source location;
- scalar, string, structured and unit function values.

Unsupported future semantics fail at compile time with `CompilationError`; the backend does not silently approximate them.

## Memory and host ABI

When strings or structured values are present, the module exports WebAssembly `memory` and an immutable `apl_static_end` global.

Compile-time strings are encoded once as deterministic UTF-8 data segments. Dynamic host-read strings are allocated after `apl_static_end` by the reference host runtime.

Arrays and records are immutable heap objects allocated through `apl.alloc(i32) -> i32`. Every element/field occupies one 8-byte slot. Record fields use lexicographic field-name order, matching normalized LIR construction. Nested arrays/records store heap pointers in those slots.

The host ABI is emitted only for imports actually needed by the module. Depending on the verified LIR it may include:

- `apl.require_capabilities(i32)`;
- `apl.console_write_i64(i64)`, `apl.console_write_bool(i32)`, `apl.console_write_string(i64)`;
- `apl.fs_read_text(i64) -> i64`, `apl.net_get_text(i64) -> i64`;
- `apl.string_eq(i64,i64) -> i32`;
- `apl.struct_eq(i64 descriptor, i32 left, i32 right) -> i32`;
- `apl.alloc(i32) -> i32`;
- `apl.application_trap(i64 code, i64 message, i64 where)`.

Drafts before APL 0.0.8 preserve their historical behavior: inferred effects may exist, but runtime capability grants are not required until the language version introduced them.

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

CI loads emitted binaries with the native Node/WebAssembly runtime and checks compiled results for arithmetic, calls, structured control, strings, arrays, records, host effects, all three resource budgets, contracts, ranges, quantities and invariants. It also validates deterministic built-in trap codes, exact application-trap diagnostics, capability denial and fixture-backed host I/O.

The core semantic WASM backend surface is now implemented. Remaining M4 work centers on systematic interpreter-vs-compiled differential testing and optimization-equivalence validation.
