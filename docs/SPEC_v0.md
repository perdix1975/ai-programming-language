# APL Specification v0

Status: **Draft 0.0.8**

This document defines the executable v0 subset of APL. The purpose of v0 is to establish stable semantic machinery before adding richer effects, contracts, capabilities, concurrency, or native compilation.

## 1. Versioning

The `apl` field is part of every program.

The current reference implementation supports:

- `0.0.1`: the original scalar/SSA semantic seed;
- `0.0.2`: a strict extension adding typed function calls and structured `if` regions;
- `0.0.3`: a strict extension adding defined integer division/remainder and ordered `i64` comparisons;
- `0.0.4`: a strict extension adding bounded structured `repeat` regions;
- `0.0.5`: a strict extension adding structured fixed-length array types and immutable array operations;
- `0.0.6`: a strict extension adding immutable structural record types and named-field access;
- `0.0.7`: a strict extension adding deterministic machine-readable traps and an explicit `trap` terminator;
- `0.0.8`: a strict extension adding exact function effects, exact module capability declarations, and explicit host grants.

Older programs retain their declared-version meaning. An operation is valid only when introduced by that program's declared version or an earlier one.

## 2. Program representation

The normative v0 interchange format is UTF-8 JSON.

A program object contains:

- `apl`: supported language version;
- `module`: non-empty module name;
- `entry`: entry function name;
- `functions`: non-empty list of function objects;
- `capabilities`: in Draft 0.0.8+, the exact sorted list of host capabilities required by the module.

The entry function must exist and require zero parameters.

## 3. Function representation

A function contains:

- `name`: unique non-empty name;
- `params`: ordered typed parameters;
- `returns`: return type;
- `effects`: in Draft 0.0.8+, the exact sorted list of host effects the function may perform directly or through calls;
- `body`: ordered instruction list.

Function declarations are visible module-wide, so a call may target a function appearing later in the file.

Draft 0.0.2 and later reject direct and mutual recursion. The module call graph must be acyclic.

## 4. Types

v0 defines:

| Type | Meaning |
|---|---|
| `i64` | signed 64-bit integer |
| `bool` | Boolean |
| `string` | Unicode string |
| `unit` | no value |
| `{"array": T, "len": N}` | immutable fixed-length array of `N` values of type `T` (0.0.5+) |
| `{"record": {"field": T, ...}}` | immutable structural record with named fields (0.0.6+) |

Integer constants are restricted to `[-2^63, 2^63-1]`.

Structured types are represented directly as JSON objects, not encoded inside strings. Array lengths are integer literals in `[0, 65_536]`. Array element types may themselves be valid non-`unit` types. Record field names are non-empty strings, each record may contain at most 256 fields, and field types may be any valid non-`unit` type. Arrays and records may therefore nest recursively.

## 5. SSA identity and regions

Value-producing instructions bind an `id`.

Within a function or structured region:

- an id is defined at most once in that environment;
- an id must be defined before use;
- parameter names share the function SSA namespace;
- branch-local bindings do not leak out of the branch;
- an `if` or `repeat` exposes only its own result id to the enclosing environment.

## 6. Core instructions

### 6.1 `const`

Creates an `i64`, `bool`, or `string`.

```json
{"op":"const","id":"x","type":"i64","value":42}
```

### 6.2 `add`, `sub`, `mul`

Require two `i64` operands and produce `i64`.

Signed overflow has defined behavior: execution traps with an APL execution error. Wraparound is not implicit.

### 6.3 `eq`

Requires two operands of identical, non-`unit` type and produces `bool`.

### 6.4 `print`

An explicit observable effect accepting one value id.

Reference rendering is:

- `bool`: `true` or `false`;
- `i64`: base-10 integer;
- `string`: string contents.

Each call emits one output line.

In Draft 0.0.8+, `print` contributes the `console.write` effect and requires the corresponding module capability plus a host runtime grant.

### 6.5 `return`

Terminates a function. A non-`unit` function returns one previously defined value of exactly the declared function return type. A `unit` function returns no value.

## 7. Draft 0.0.2 instructions

### 7.1 `call`

A call names a module function and supplies SSA ids as arguments.

```json
{
  "op":"call",
  "id":"answer",
  "type":"i64",
  "function":"choose",
  "args":["flag","x","y"]
}
```

Verification requires:

- target function exists;
- argument count matches exactly;
- each argument type matches its parameter type exactly;
- a non-`unit` result binds an id with the exact declared return type;
- a `unit` result binds no id;
- the complete module call graph remains acyclic.

### 7.2 structured `if`

Draft 0.0.2 `if` is a value-producing structured region.

```json
{
  "op":"if",
  "id":"selected",
  "type":"i64",
  "cond":"flag",
  "then":[{"op":"yield","value":"a"}],
  "else":[{"op":"yield","value":"b"}]
}
```

Rules:

- `cond` must reference `bool`;
- `type` must currently be non-`unit`;
- both branches are non-empty instruction lists;
- each branch terminates with `yield`;
- both yielded values must exactly match the `if` result type;
- only the selected branch executes;
- branch-local SSA bindings do not escape;
- effects in the unselected branch do not occur.

### 7.3 `yield`

`yield` is a structured-region terminator. In 0.0.2 it terminates an `if` branch; in 0.0.4 it also terminates a `repeat` body iteration. It yields one SSA value to the enclosing structured operation.

It is not a function return.

## 8. Draft 0.0.3 instructions

### 8.1 `div`

`div` requires two `i64` operands and produces `i64`. Division truncates toward zero.

Defined traps:

- divisor equal to zero -> execution error;
- `INT64_MIN / -1` -> signed `i64` overflow execution error.

No host-language or target-CPU division semantics may override these rules.

### 8.2 `rem`

`rem` requires two `i64` operands and produces `i64`. For nonzero divisor it is defined by the truncating quotient:

`r = a - trunc(a / b) * b`

The sign of a nonzero remainder therefore follows the dividend. Division by zero traps. The edge case `INT64_MIN rem -1` is explicitly defined as `0` and does not overflow.

### 8.3 ordered comparisons

`lt`, `le`, `gt`, and `ge` each require two `i64` operands and produce `bool`. They use ordinary signed mathematical integer ordering.

## 9. Draft 0.0.4 instructions

### 9.1 bounded `repeat`

`repeat` is a value-producing structured iteration region with an explicit static execution bound.

```json
{
  "op":"repeat",
  "id":"factorial",
  "type":"i64",
  "count":"n",
  "max":10,
  "init":"one",
  "index":"i",
  "carry":"acc",
  "body":[
    {"op":"add","id":"factor","type":"i64","args":["i","one"]},
    {"op":"mul","id":"next","type":"i64","args":["acc","factor"]},
    {"op":"yield","value":"next"}
  ]
}
```

Verification requires that `count` is `i64`; `max` is an integer literal in `[0, 1_000_000]`; `init` is non-`unit`; the result type equals the `init` type; `index` and `carry` are distinct region-local names that do not collide with outer SSA ids; and the body ends in a `yield` of the carried type.

Execution first validates the runtime count. A negative count, or a count greater than `max`, traps before any body effect. Otherwise the body executes exactly `count` times. The iteration index is zero-based. The first `carry` is `init`; each body `yield` becomes the next carry. Each iteration receives a fresh region-local SSA environment. The final carry is the operation result. For `count = 0`, the body does not execute and the result is exactly `init`.

Because every verified `repeat` contains a statically capped `max`, it cannot execute an unbounded number of iterations.

## 10. Draft 0.0.5 instructions

### 10.1 structured fixed-array type

A fixed-array type is represented as:

```json
{"array":"i64","len":3}
```

The descriptor contains exactly two keys: `array` for the element type and `len` for the exact length. Length is part of the type, so arrays of lengths 3 and 4 are distinct types.

Array values are immutable. Mutation is not part of Draft 0.0.5.

### 10.2 `array`

Constructs an immutable fixed-length array from existing SSA values.

```json
{
  "op":"array",
  "id":"items",
  "type":{"array":"i64","len":3},
  "args":["a","b","c"]
}
```

Verification requires the number of arguments to exactly match the type length and every argument type to exactly match the element type.

### 10.3 `array.get`

Reads one element by runtime `i64` index.

```json
{"op":"array.get","id":"x","type":"i64","args":["items","index"]}
```

The index is zero-based. If the index is negative or greater than or equal to the fixed length, execution traps with an APL execution error. Negative indices never wrap from the end.

### 10.4 `array.len`

Returns the exact fixed length as an `i64`.

```json
{"op":"array.len","id":"n","type":"i64","args":["items"]}
```

### 10.5 equality

Two arrays may be compared with `eq` when their complete types are identical. Equality is structural and element-wise. Nested fixed arrays therefore compare recursively.

### 10.6 function and region typing

Structured array types may be used in function parameters, function return types, `if` results, and `repeat` carried values. Exact structural type equality is required; there are no implicit array conversions.

`print` remains scalar-only in Draft 0.0.6.

## 11. Draft 0.0.6 instructions

### 11.1 structural record type

A record type is represented as:

```json
{
  "record": {
    "name": "string",
    "age": "i64"
  }
}
```

Record types are structural. Field order is not part of the type: two record descriptors with the same field names and exactly equal field types denote the same type regardless of JSON member order.

Record field names must be non-empty strings. A record may contain at most 256 fields. Empty records are valid. Record fields may not have type `unit`.

### 11.2 `record`

Constructs an immutable record from existing SSA values.

```json
{
  "op":"record",
  "id":"person",
  "type":{"record":{"name":"string","age":"i64"}},
  "fields":{"name":"name_value","age":"age_value"}
}
```

Verification requires the supplied field-name set to exactly equal the type's field-name set. Each field source must be an SSA id whose type exactly matches the declared field type. There are no optional, implicit, or extra fields in Draft 0.0.6.

### 11.3 `record.get`

Reads one field named by a compile-time string literal.

```json
{
  "op":"record.get",
  "id":"age",
  "type":"i64",
  "record":"person",
  "field":"age"
}
```

The source must be a record and the requested field must exist in its type. The result type is exactly the declared field type. Because field membership is checked by the verifier, a verified `record.get` does not perform a missing-field runtime trap.

### 11.4 equality and canonical field order

Records of exactly equal structural type may be compared with `eq`. Equality is recursive and field-wise. Runtime field storage order is not observable and does not affect equality.

The reference interpreter stores record fields in deterministic lexicographic field-name order. This is an implementation strategy consistent with the semantics, not a user-visible ordering guarantee.

### 11.5 nesting and function/region typing

Records may contain arrays or other records, and arrays may contain records. Record types may be used in function parameters/returns, `if` results, and `repeat` carried values. Exact structural type equality is required throughout.

Records are immutable values. Draft 0.0.6 defines no field mutation operation.

## 12. Draft 0.0.7 trap model

### 12.1 deterministic trap

A **trap** is abrupt program termination with three observable diagnostic components:

- `code`: a stable machine-readable identifier;
- `message`: human-readable diagnostic text;
- `where`: the logical IR execution location reported by the runtime.

A trap produces no normal value. Draft 0.0.7 defines no catch, recovery, resume, or handler mechanism: a trap propagates through structured regions and function calls until execution of the whole program terminates.

The stable semantic interface is the trap `code`. Diagnostic wording may be improved in future compatible implementations without changing the meaning of the code.

### 12.2 explicit `trap`

User programs may terminate deliberately:

```json
{
  "op":"trap",
  "code":"app.invalid_state",
  "message":"invalid state"
}
```

`trap` is a block terminator. It may terminate a function body, an `if` branch, or a `repeat` body in place of that block's ordinary `return` or `yield`. Instructions after it in the same block are invalid.

User-defined trap codes:

- must match `[a-z][a-z0-9_.-]{0,63}`;
- must not equal `apl` or begin with the reserved `apl.` namespace.

The explicit message must contain from 1 through 512 Unicode code points.

### 12.3 reserved runtime trap codes

The `apl.*` namespace is reserved by the language/runtime. Draft 0.0.7 standardizes these runtime trap codes:

| Code | Condition |
|---|---|
| `apl.i64_overflow` | a trapping signed `i64` operation overflows |
| `apl.division_by_zero` | `div` or `rem` uses divisor zero |
| `apl.array_index_oob` | `array.get` index is negative or at least the array length |
| `apl.repeat_negative_count` | `repeat` runtime count is negative |
| `apl.repeat_count_exceeds_max` | `repeat` runtime count exceeds its declared static `max` |
| `apl.capability_denied` | a 0.0.8+ execution lacks a required host capability grant |

These codes replace no prior semantics: they assign stable identities to execution failures whose conditions were already defined in earlier drafts.

The reference implementation also uses `apl.internal_invalid_execution` as a defensive implementation guard. A verified conforming program must not reach that condition; it is not an ordinary language-level trap that programs should depend on.

### 12.4 logical location

The reference location format identifies the dynamic structured IR position using function and instruction-region paths, for example:

```text
main[2]
main[1].then[0]
main[3].body[2]
```

The location is diagnostic metadata. It is not part of type identity, canonical program identity, or the stable trap-code namespace.

### 12.5 side effects and propagation

Effects completed before a trap remain completed. Instructions and effects after the trapping instruction do not execute. An unselected `if` branch still does not execute, so a `trap` in an unselected branch has no effect.

For runtime precondition traps that are specified to occur before entering a region, such as invalid `repeat` count, no body effect occurs before the trap.

## 13. Draft 0.0.8 effects and capabilities

### 13.1 purpose

Draft 0.0.8 separates three concepts that must not be conflated:

1. **inferred effects**: host-visible effects reachable from a function body;
2. **declared effects**: the function's exact static effect contract;
3. **runtime grants**: capabilities the host actually authorizes for this execution.

A declaration never grants authority by itself.

### 13.2 function `effects`

Every 0.0.8+ function contains an `effects` list.

```json
{
  "name":"emit",
  "params":[{"name":"message","type":"string"}],
  "returns":"unit",
  "effects":["console.write"],
  "body":[
    {"op":"print","args":["message"]},
    {"op":"return"}
  ]
}
```

The list must:

- contain only effects defined by the declared language version;
- be lexicographically sorted;
- contain no duplicates;
- exactly equal the verifier-inferred effect set of the function.

A pure function therefore declares `"effects":[]`.

Effects propagate transitively through function calls. Structured regions contribute the union of effects in all statically possible branches/bodies, regardless of which branch is selected at runtime. This makes the effect contract conservative and execution-independent.

Draft 0.0.8 defines one host effect:

| Effect | Introduced by |
|---|---|
| `console.write` | `print` |

### 13.3 module `capabilities`

Every 0.0.8+ program contains a module-level `capabilities` list.

```json
"capabilities":["console.write"]
```

It must be the exact lexicographically sorted, duplicate-free union of every function's declared effects. Extra capabilities are rejected as over-declaration; missing capabilities are rejected as under-declaration.

Thus a module's static authority footprint is explicit in canonical IR and participates in canonical identity/hash.

### 13.4 runtime host grants

Verification proves what authority a program declares it needs. Execution separately receives a set of capabilities granted by the host.

Before executing the entry function of a 0.0.8+ program, the runtime verifies that every declared module capability is present in the host grant set. If any required capability is absent, execution traps before program effects begin with:

```text
apl.capability_denied
```

Hosts may grant a superset, but the program may use only effects present in its verified module declaration.

The reference CLI grants capabilities explicitly with repeatable `--allow` arguments, for example:

```text
apl run examples/effects.apl --allow console.write
```

### 13.5 compatibility

Programs declaring APL 0.0.1 through 0.0.7 retain their earlier semantics. They are not retroactively required to contain `effects` or `capabilities`, and their legacy `print` behavior is unchanged.

### 13.6 security boundary

Effect annotations are a static audit contract. Capability declarations are the module's requested authority. Host grants are the enforcement boundary.

A conforming 0.0.8 runtime must not perform a protected host effect without the corresponding grant, even if the program has a syntactically valid capability declaration.

## 14. Verification

A conforming verifier rejects at least:

- unsupported versions;
- malformed program/function/instruction structures;
- duplicate functions;
- missing or parameterized entry functions;
- unsupported types or operations;
- duplicate SSA ids;
- use-before-definition;
- operand/result type mismatches;
- invalid block terminators;
- return/yield type mismatches;
- unknown function targets;
- call arity/type mismatches;
- recursive call cycles;
- use of an operation before the language version that introduced it.

Execution is defined only for verified programs.

## 15. Canonical textual representation

The v0 canonical encoding is JSON with:

- object keys sorted lexicographically;
- no insignificant whitespace;
- UTF-8 output;
- non-ASCII characters retained;
- NaN and Infinity forbidden.

Canonical identity is SHA-256 over the UTF-8 bytes of that encoding.

This is an encoding identity, not yet a proof of semantic equivalence between differently structured programs.

## 16. Reference implementation

The Python implementation under `src/apl` is the executable reference for the current draft. Tests under `tests/` form a growing conformance suite.

## 17. Deliberately absent

Not yet defined:

- general recursion;
- unbounded/general loops;
- algebraic data types;
- trap recovery, handlers, and resumable exceptions;
- contracts and refinement types;
- filesystem/network/database capability semantics;
- file/network/database access;
- concurrency;
- resource bounds;
- module imports;
- binary canonical IR;
- optimizer/compiler backends;
- AI-generated primitives.

Conventional-language behavior for these features must not be assumed until formally specified.
